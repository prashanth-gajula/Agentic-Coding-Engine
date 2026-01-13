class Node:
    """
    A class representing a node in a linked list.
    """
    def __init__(self, data):
        self.data = data  # Data stored in the node
        self.next = None  # Pointer to the next node

class LinkedList:
    """
    A class representing a linked list.
    """
    def __init__(self):
        self.head = None  # Head of the list

    def insert_node(self, data):
        """
        Insert a new node with the given data at the end of the list.
        """
        new_node = Node(data)
        if not self.head:
            self.head = new_node
            return
        last_node = self.head
        while last_node.next:
            last_node = last_node.next
        last_node.next = new_node

    def delete_node(self, key):
        """
        Delete the first node with the specified data.
        """
        temp = self.head
        if temp is not None:
            if temp.data == key:
                self.head = temp.next  # Change head if the node to be deleted is head
                temp = None  # Free memory
                return
        while temp is not None:
            if temp.data == key:
                break
            prev = temp
            temp = temp.next
        if temp == None:
            return  # Key not found
        prev.next = temp.next
        temp = None  # Free memory

    def display_list(self):
        """
        Display the linked list.
        """
        current_node = self.head
        while current_node:
            print(current_node.data, end=" -> ")
            current_node = current_node.next
        print("None")  # Indicate the end of the list

# Example usage:
# linked_list = LinkedList()
# linked_list.insert(10)
# linked_list.insert(20)
# linked_list.insert(30)
# linked_list.display()  # Output: 10 -> 20 -> 30 -> None
# linked_list.delete(20)
# linked_list.display()  # Output: 10 -> 30 -> None