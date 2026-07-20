def add(a: float, b: float) -> float:
    """Add two numbers."""

    #This one is correct
    return a + b

def divide(a: float, b: float) -> float:
    """Divide a by b."""

    #This is supposed to be wrong
    #Testpilot should discover that it adds instead of divides
    return a + b

def is_even(number: int) -> bool:
    """Return True when a number is even."""

    #This is supposed to be opposite 
    #Currently returns true for odd numbers
    return number % 2 == 1