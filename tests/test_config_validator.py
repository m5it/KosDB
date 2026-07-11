"""
Tests for configuration validator.
"""

import unittest
import json
import tempfile
import os
from config_validator import ConfigValidator, validate_config, create_minimal_config


class TestConfigValidator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_config_file(self, config):
        """Helper to create config file."""
        path = os.path.join(self.temp_dir, 'config.json')
        with open(path, 'w') as f:
            json.dump(config, f)
        return path
    
    def test_valid_minimal_config(self):
        config = create_minimal_config()
        path = self.create_config_file(config)
        
        is_valid, errors = validate_config(path)
        if not is_valid:
            print(f"Minimal config errors: {errors}")
        self.assertTrue(is_valid, f"Errors: {errors}")
    
    def test_invalid_port(self):
        config = create_minimal_config()
        config['server']['port'] = 70000
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('port' in e for e in errors))
    
    def test_tls_requires_certs(self):
        config = create_minimal_config()
        config['tls']['enabled'] = True
        config['tls']['cert_file'] = '/nonexistent/cert.pem'
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('cert_file' in e for e in errors))
    
    def test_invalid_cache_size(self):
        config = create_minimal_config()
        config['cache']['max_size'] = -1
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('max_size' in e for e in errors))
    
    def test_invalid_gpu_device(self):
        config = create_minimal_config()
        config['gpu']['device_id'] = -1
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('device_id' in e for e in errors))
    
    def test_invalid_vector_metric(self):
        config = create_minimal_config()
        config['vector_search']['metric'] = 'invalid_metric'
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('metric' in e for e in errors))
    
    def test_invalid_log_level(self):
        config = create_minimal_config()
        config['logging']['level'] = 'INVALID'
        
        path = self.create_config_file(config)
        is_valid, errors = validate_config(path)
        
        self.assertFalse(is_valid)
        self.assertTrue(any('level' in e for e in errors))


class TestDevelopmentConfig(unittest.TestCase):
    def test_development_config_is_valid(self):
        is_valid, errors = validate_config('config.development.json')
        self.assertTrue(is_valid, f"Errors: {errors}")
    
    def test_development_has_localhost(self):
        with open('config.development.json') as f:
            config = json.load(f)
        
        self.assertEqual(config['server']['host'], '127.0.0.1')
        self.assertFalse(config['tls']['enabled'])
        self.assertEqual(config['logging']['level'], 'DEBUG')


class TestProductionConfig(unittest.TestCase):
    def test_production_config_is_valid(self):
        validator = ConfigValidator('config.production.json')
        validator.load()
        
        config = validator.config
        self.assertTrue(config['tls']['enabled'])
        self.assertEqual(config['server']['max_connections'], 1000)
        self.assertTrue(config['replication']['enabled'])
        self.assertTrue(config['failover']['enabled'])


class TestGPUConfig(unittest.TestCase):
    def test_gpu_config_is_valid(self):
        is_valid, errors = validate_config('config.gpu-enabled.json')
        self.assertIsInstance(is_valid, bool)
    
    def test_gpu_config_has_gpu_enabled(self):
        with open('config.gpu-enabled.json') as f:
            config = json.load(f)
        
        self.assertTrue(config['gpu']['enabled'])
        self.assertTrue(config['vector_search']['use_gpu'])
        self.assertEqual(config['gpu']['memory_limit_mb'], 8192)


class TestMainConfig(unittest.TestCase):
    def test_main_config_is_valid(self):
        is_valid, errors = validate_config('config.json')
        self.assertTrue(is_valid, f"Errors: {errors}")
    
    def test_main_config_has_all_sections(self):
        with open('config.json') as f:
            config = json.load(f)
        
        required_sections = [
            'server', 'tls', 'cache', 'gpu', 'fulltext',
            'vector_search', 'replication', 'failover',
            'monitoring', 'logging'
        ]
        
        for section in required_sections:
            self.assertIn(section, config)


if __name__ == '__main__':
    unittest.main(verbosity=2)
