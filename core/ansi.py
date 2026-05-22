"""ANSI colour helpers — stdlib only."""

R   = '\033[0;31m'
G   = '\033[0;32m'
Y   = '\033[1;33m'
C   = '\033[0;36m'
B   = '\033[1m'
DIM = '\033[2m'
NC  = '\033[0m'

def red(s):    return f"{R}{s}{NC}"
def green(s):  return f"{G}{s}{NC}"
def yellow(s): return f"{Y}{s}{NC}"
def cyan(s):   return f"{C}{s}{NC}"
def bold(s):   return f"{B}{s}{NC}"
def dim(s):    return f"{DIM}{s}{NC}"
