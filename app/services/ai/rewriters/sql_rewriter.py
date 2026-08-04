import logging
import sqlglot
from sqlglot import exp, parse_one
from typing import Optional, Dict, List, Any, Set
import re

logger = logging.getLogger(__name__)

class SQLRewriteError(Exception):
    """Exception raised when SQL rewriting fails."""
    pass

class SQLRewriter:
    """SQL 重写引擎，支持字段存在性检查和智能表匹配"""

    def __init__(self, dialect: str = "clickhouse", table_metadata: Optional[Dict[str, Set[str]]] = None):
        self.dialect = dialect
        self.table_metadata = table_metadata or {}

    def set_table_metadata(self, table_metadata: Dict[str, Set[str]]):
        """设置表元数据，用于字段校验"""
        self.table_metadata = table_metadata

    def rewrite(
        self,
        sql: str,
        filters: List[Dict[str, Any]],
        user_context: Dict[str, Any],
        is_admin: bool = False
    ) -> str:
        """SQL 重写：添加字段验证和智能表匹配"""
        if not filters or is_admin:
            return sql

        try:
            # 1. 解析SQL为AST，提取查询的表
            expression = sqlglot.parse_one(sql, read=self.dialect)
            query_tables = self._extract_query_tables(expression)

            # 2. 智能过滤：只应用相关的条件
            relevant_filters = self._filter_relevant_conditions(filters, query_tables)
            if not relevant_filters:
                logger.info(f"[SQLRewriter] No relevant filters found for tables: {query_tables}")
                return sql

            # 3. 处理过滤条件（替换变量 + 字段验证）
            processed_conditions = self._prepare_conditions_with_validation(relevant_filters, user_context, query_tables)
            if not processed_conditions:
                return sql

            # 4. 应用条件到AST
            def transform_node(node):
                if isinstance(node, exp.Select):
                    new_node = node.copy()
                    for cond in processed_conditions:
                        new_node = new_node.where(cond, append=True)
                    return new_node
                return node

            expression = expression.transform(transform_node)

            # 5. 生成最终SQL
            result_sql = expression.sql(dialect=self.dialect)

            # 6. 记录应用的条件信息
            applied_count = len(processed_conditions)
            skipped_count = len(filters) - applied_count
            logger.info(f"[SQLRewriter] Applied {applied_count} filters, skipped {skipped_count} invalid filters")

            return result_sql
        except Exception as e:
            logger.error(f"[SQLRewriter] Failed to rewrite SQL: {e}", exc_info=True)
            raise SQLRewriteError(f"SQL transformation failed: {str(e)}")

    def _extract_query_tables(self, expression: exp.Expression) -> Set[str]:
        """从SQL AST中提取所有涉及的表名"""
        tables = set()

        # 直接查找所有Table节点
        for node in expression.find_all(exp.Table):
            # 获取表名的原始文本（处理引号）
            if isinstance(node.this, exp.Identifier):
                table_name = node.this.this
            else:
                table_name = str(node.this)

            # 移除可能的引号和大小写标准化（取决于方言，这里统一转小写进行匹配）
            table_name = table_name.strip('"`[]').lower()
            if table_name:
                tables.add(table_name)

        return tables

    def _filter_relevant_conditions(self, filters: List[Dict[str, Any]], query_tables: Set[str]) -> List[Dict[str, Any]]:
        """智能过滤：只返回与查询表相关的条件"""
        relevant_filters = []

        # 将查询表名统一转小写以进行不区分大小写的匹配
        query_tables_lower = {t.lower() for t in query_tables}

        for f in filters:
            condition = f.get("condition", "")
            target_table = str(f.get("target_table", "all")).lower()

            # 1. 显式指定的 target_table 校验
            if target_table != "all":
                if target_table not in query_tables_lower:
                    logger.debug(f"[SQLRewriter] Skipping filter for table '{target_table}' not in query {query_tables_lower}")
                    continue

            # 2. 从条件中提取涉及的表名
            condition_tables = self._extract_tables_from_condition(condition)
            condition_tables_lower = {t.lower() for t in condition_tables}

            # 3. 逻辑判定：
            # - 如果条件没有指定表名 (如 "status=1")，默认认为相关
            # - 如果条件指定了表名，且表名在查询涉及的表中，则相关
            if not condition_tables_lower or (condition_tables_lower & query_tables_lower):
                relevant_filters.append(f)
            else:
                logger.info(f"[SQLRewriter] Skipping unrelated filter: '{condition}' (Tables: {condition_tables_lower})")

        return relevant_filters

    def _extract_tables_from_condition(self, condition: str) -> Set[str]:
        """从条件字符串中提取表名"""
        tables = set()

        # 1. 首先移除所有 {user.xxx} 占位符，防止误匹配
        clean_condition = re.sub(r'\{user\.\w+\}', '', condition)

        # 2. 匹配 tablename.fieldname 或 "tablename".fieldname 或 [tablename].fieldname 模式
        table_field_pattern = r'(?:["`\[])?([a-zA-Z_][a-zA-Z0-9_]*)(?:["`\]])?\.[a-zA-Z_][a-zA-Z0-9_]*'
        matches = re.findall(table_field_pattern, clean_condition)

        for m in matches:
            tables.add(m.lower())

        return tables

    def _prepare_conditions(self, filters: List[Dict[str, Any]], context: Dict[str, Any]) -> List[exp.Expression]:
        """兼容旧版测试的方法名"""
        return self._prepare_conditions_with_validation(filters, context, set())

    def _prepare_conditions_with_validation(
        self,
        filters: List[Dict[str, Any]],
        context: Dict[str, Any],
        query_tables: Set[str]
    ) -> List[exp.Expression]:
        """处理条件并验证字段存在性"""
        prepared = []

        for f in filters:
            cond_str = f.get("condition")
            if not cond_str:
                continue

            # 1. 替换用户变量
            temp_cond = self._replace_user_variables(cond_str, context)

            # 2. 验证字段存在性 (只有在提供了 query_tables 时才验证)
            if not query_tables or self._validate_condition_fields(temp_cond, query_tables):
                try:
                    cond_expr = sqlglot.parse_one(temp_cond, read=self.dialect)
                    prepared.append(cond_expr)
                    logger.debug(f"[SQLRewriter] Applied condition: {temp_cond}")
                except Exception as e:
                    logger.warning(f"[SQLRewriter] Failed to parse condition '{temp_cond}': {e}")
            else:
                logger.warning(f"[SQLRewriter] Skipping invalid condition due to field validation: {temp_cond}")

        return prepared

    def _replace_user_variables(self, condition: str, context: Dict[str, Any]) -> str:
        """替换用户变量占位符"""
        placeholders = re.findall(r"\{user\.(\w+)\}", condition)
        temp_cond = condition

        for key in placeholders:
            val = context.get(key)

            if isinstance(val, str):
                pattern_with_quotes = f"'{{user.{key}}}'"
                if pattern_with_quotes in temp_cond:
                    temp_cond = temp_cond.replace(f"{{user.{key}}}", str(val))
                else:
                    temp_cond = temp_cond.replace(f"{{user.{key}}}", f"'{val}'")
            else:
                repl_val = str(val) if val is not None else "NULL"
                temp_cond = temp_cond.replace(f"{{user.{key}}}", repl_val)

        return temp_cond

    def _validate_condition_fields(self, condition: str, query_tables: Set[str]) -> bool:
        """验证条件中的字段是否在查询表中存在"""
        if not self.table_metadata:
            # 如果没有元数据，跳过验证
            return True

        # 提取条件中的所有字段引用
        field_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(field_pattern, condition)

        if not matches:
            # 如果没有明确的表.字段格式，可能是无表前缀的字段，暂时允许通过
            return True

        for table_name, field_name in matches:
            # 检查表是否在查询中
            if table_name not in query_tables:
                logger.debug(f"[SQLRewriter] Field {table_name}.{field_name} references table not in query: {query_tables}")
                return False

            # 检查字段是否在表中存在
            if table_name in self.table_metadata:
                if field_name not in self.table_metadata[table_name]:
                    logger.debug(f"[SQLRewriter] Field {field_name} not found in table {table_name}")
                    return False

        return True

    @staticmethod
    def resolve_strategy(user_id: int, roles: List[str], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        实现分层策略解析：用户 > 角色 > 默认
        """
        if not config:
            return []

        # 1. 用户例外策略（最高优先级）
        user_overrides = config.get("user_overrides", {})
        if str(user_id) in user_overrides:
            return user_overrides[str(user_id)]

        # 2. 角色策略（多角色UNION）
        role_policies = config.get("role_policies", {})
        active_rules = []
        matched_any = False

        for r in roles:
            if r in role_policies:
                matched_any = True
                rules = role_policies[r]
                # 如果任何角色是admin或有空规则（完全访问），返回空
                if not rules:
                    return []
                active_rules.extend(rules)

        if matched_any:
            return active_rules

        # 3. 默认策略（兜底）
        return config.get("default_policy", [{"condition": "1=0"}])