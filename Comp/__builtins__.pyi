# Makes pylance happy to find the _ function in the builtins module
# because getext.install injects it into it

def _(msg: str, /) -> str: ...
