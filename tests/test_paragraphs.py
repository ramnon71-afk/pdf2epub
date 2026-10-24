import unittest
from pdf2epub import split_readable_paragraphs

class ParagraphTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_readable_paragraphs('Prima frase.  Seconda frase!  Terza?  Quarta.'), ['Prima frase.', 'Seconda frase!', 'Terza?', 'Quarta.'])
    def test_no_split_single_space(self):
        self.assertEqual(split_readable_paragraphs('Prima. Seconda.'), ['Prima. Seconda.'])
    def test_no_split_wrapped_word(self):
        self.assertEqual(split_readable_paragraphs('la  mazza'), ['la mazza'])
