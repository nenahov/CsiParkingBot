import re


class HandlerFunction:
    def __init__(self, pattern: str, func):
        self.pattern = pattern
        self.func = func


class HandlerFunctions:
    def __init__(self):
        self.__handlers = list()

    def add_handler(self, pattern: str, func):
        self.__handlers.append(HandlerFunction(pattern, func))

    async def call_handler_func_by_text(self, message, session, driver):
        text = message.text
        if (text is None) or (len(text) == 0):
            return
        for handler in self.__handlers:
            match = re.search(handler.pattern, text, re.IGNORECASE)
            if match:
                await handler.func(message, match, session, driver)
                return
        # Ничего не нашли
        pass
