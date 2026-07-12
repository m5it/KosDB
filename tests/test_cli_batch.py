"""
Tests for CLI batch functionality.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCLIBatch(unittest.TestCase):
    """Test CLI batch features."""
    
    def test_batch_file_reader(self):
        """Test reading batch from file."""
        from cli import read_batch_file
        
        # Create temp file
        test_content = """SELECT 1;
SELECT 2;
-- This is a comment
SELECT 3;"""
        
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write(test_content)
            temp_path = f.name
        
        try:
            result = read_batch_file(temp_path)
            self.assertIn('SELECT 1', result)
            self.assertIn('SELECT 2', result)
            self.assertIn('SELECT 3', result)
            self.assertNotIn('comment', result)
        finally:
            os.unlink(temp_path)
    
    def test_batch_file_not_found(self):
        """Test error handling for missing file."""
        from cli import read_batch_file
        result = read_batch_file('/nonexistent/file.sql')
        self.assertEqual(result, "")


if __name__ == '__main__':
    unittest.main()
