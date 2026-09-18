from calculator import calculate_average


def test_empty_list():
    assert calculate_average([]) == 0


def test_nonempty_list():
    assert calculate_average([2, 4, 6]) == 4


def test_negative_numbers():
    assert calculate_average([-4, -2]) == -3
