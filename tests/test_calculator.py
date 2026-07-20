#Create bugs so the Testpilot can detect them 

from sample_app.calculator import add, divide, is_even

def test_add():
    #This test should pass
    assert add(2, 3) == 5

def test_divide():
    #Answer is 5 but will be incorrect
    assert divide(10, 2) == 5

def test_even_number():
    #4 is even
    assert is_even(4) is True  

def test_odd_number():
    #5 not even 
    assert is_even is False