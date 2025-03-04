class AgentError(Exception):
    """自定义异常基类"""
    pass


class BrowserOperationError(AgentError):
    """浏览器操作异常"""
    pass
