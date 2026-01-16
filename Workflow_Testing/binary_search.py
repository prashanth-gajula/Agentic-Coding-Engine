def binary_search(arr, target, low=0, high=None):
    """
    Perform a recursive binary search.
    :param arr: List of sorted elements
    :param target: Element to search for
    :param low: Starting index of the search
    :param high: Ending index of the search
    :return: Index of target element if found, else -1
    """
    if high is None:
        high = len(arr) - 1
    if low > high:
        return -1  # Base case: target not found
    mid = (low + high) // 2
    if arr[mid] == target:
        return mid  # Target found
    elif arr[mid] < target:
        return binary_search(arr, target, mid + 1, high)  # Search in the right half
    else:
        return binary_search(arr, target, low, mid - 1)  # Search in the left half
