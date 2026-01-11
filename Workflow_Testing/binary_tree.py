class Node:
    def __init__(self, key):
        self.left = None
        self.right = None
        self.value = key

class BinaryTree:
    def __init__(self):
        self.root = None

    def insert(self, key):
        if self.root is None:
            self.root = Node(key)
        else:
            self._insert_recursive(self.root, key)

    def _insert_recursive(self, current_node, key):
        if key < current_node.value:
            if current_node.left is None:
                current_node.left = Node(key)
            else:
                self._insert_recursive(current_node.left, key)
        else:
            if current_node.right is None:
                current_node.right = Node(key)
            else:
                self._insert_recursive(current_node.right, key)

    def search(self, key):
        return self._search_recursive(self.root, key)

    def _search_recursive(self, current_node, key):
        if current_node is None:
            return False
        if key == current_node.value:
            return True
        elif key < current_node.value:
            return self._search_recursive(current_node.left, key)
        else:
            return self._search_recursive(current_node.right, key)

    def in_order_traversal(self, node, visit):
        if node:
            self.in_order_traversal(node.left, visit)
            visit(node.value)
            self.in_order_traversal(node.right, visit)

    def pre_order_traversal(self, node, visit):
        if node:
            visit(node.value)
            self.pre_order_traversal(node.left, visit)
            self.pre_order_traversal(node.right, visit)

    def post_order_traversal(self, node, visit):
        if node:
            self.post_order_traversal(node.left, visit)
            self.post_order_traversal(node.right, visit)
            visit(node.value)
