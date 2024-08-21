Overview

The Library Management System is designed to manage the checkout and return of books in a library. It uses a dictionary to keep track of the books and their availability. The system allows users to check out books, return books, and view the status of books in the library.
Purpose

The primary purpose of this system is to simplify and automate the process of managing books in a library. It helps in:

    Checking out books to users.
    Returning books back to the library.
    Keeping track of which books are currently available and which are checked out.

Functionality

The system includes the following functionalities:

    Check Out a Book
    Return a Book
    View the Status of a Book

Data Structure

    Library Dictionary: Stores the status of each book.
        Key: Book title (string)
        Value: Availability status (True for available, False for checked out)

Functions
1. check_out(book_title)

Purpose: To check out a book from the library.

Inputs:

    book_title (str): The title of the book to be checked out.

Steps:

    Check if the book exists in the library.
    If the book is in the library and is available (True), mark it as checked out (False) and confirm the checkout.
    If the book is already checked out, inform the user.
    If the book is not in the library, inform the user.
    2. return_book(book_title)

Purpose: To return a book to the library.

Inputs:

    book_title (str): The title of the book to be returned.

Steps:

    Check if the book exists in the library.
    If the book is in the library and is currently checked out (False), mark it as available (True) and confirm the return.
    If the book was already available (True), inform the user that the book is already in the library.
    If the book is not in the library, inform the user.
    Usage

    Checking Out a Book:
        Call check_out("Book Title") to attempt to check out a book with the given title.
        The function will notify if the book is successfully checked out or if it is already checked out or not in the library.

    Returning a Book:
        Call return_book("Book Title") to return a book with the given title.
        The function will notify if the book is successfully returned or if it was already in the library or not in the library.
Summary

The Library Management System provides a simple interface for managing book checkouts and returns. It uses a dictionary to track book availability and ensures that users can only check out and return books according to their current status.
