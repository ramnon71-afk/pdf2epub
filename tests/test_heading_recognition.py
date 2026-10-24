"""Regression tests for chapter headings in extracted PDF text."""
import unittest

from pdf2epub import heading_or_split, reconstruct


class HeadingRecognitionTests(unittest.TestCase):
    def test_escaped_dot_and_inline_body(self):
        result = heading_or_split(r"1\. The opening.  A new character enters the room.")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "1. The opening.")
        self.assertEqual(result[1], "A new character enters the room.")

    def test_trailing_chapter_heading_keeps_previous_text(self):
        items, _ = reconstruct([
            "The first scene ends. The narrator closes the notebook. 12. A new beginning.",
            "The next scene begins in the morning."
        ])
        headings = [value for kind, value in items if kind == "heading"]
        self.assertIn("12. A new beginning.", headings)
        paragraphs = [value for kind, value in items if kind == "paragraph"]
        self.assertTrue(any("The narrator closes the notebook." in value for value in paragraphs))

    def test_standalone_heading(self):
        self.assertEqual(heading_or_split("2. A different place."), ("2. A different place.", None))


if __name__ == "__main__":
    unittest.main()
