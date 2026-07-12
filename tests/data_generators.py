
"""
Test Data Generators for Acceptance Tests

Generates realistic test data for batch operation testing.
"""

import random
import string
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta


class TestDataGenerator:
    """Base class for test data generators."""
    
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        """Generate test data."""
        raise NotImplementedError


class UserDataGenerator(TestDataGenerator):
    """Generate user test data."""
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        users = []
        for i in range(count):
            user = {
                'id': i + 1,
                'username': f'user_{i}_{self.random.randint(1000, 9999)}',
                'email': f'user{i}@example.com',
                'created_at': (datetime.now() - timedelta(days=self.random.randint(1, 365))).isoformat(),
                'active': self.random.choice([True, False]),
                'profile': {
                    'name': f'User {i}',
                    'age': self.random.randint(18, 80),
                    'country': self.random.choice(['US', 'UK', 'CA', 'DE', 'FR'])
                }
            }
            users.append(user)
        return users


class OrderDataGenerator(TestDataGenerator):
    """Generate order test data."""
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        orders = []
        for i in range(count):
            order = {
                'id': i + 1,
                'user_id': self.random.randint(1, 1000),
                'amount': round(self.random.uniform(10.0, 500.0), 2),
                'status': self.random.choice(['pending', 'completed', 'cancelled']),
                'items': self.random.randint(1, 10),
                'created_at': datetime.now().isoformat()
            }
            orders.append(order)
        return orders


class CDCEventGenerator(TestDataGenerator):
    """Generate CDC change events."""
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        events = []
        tables = ['users', 'orders', 'products', 'inventory']
        operations = ['INSERT', 'UPDATE', 'DELETE']
        
        for i in range(count):
            table = self.random.choice(tables)
            operation = self.random.choice(operations)
            
            event = {
                'id': i + 1,
                'table': table,
                'operation': operation,
                'timestamp': datetime.now().isoformat(),
                'data': self._generate_event_data(table, operation),
                'previous_data': None if operation == 'INSERT' else {'id': i + 1}
            }
            events.append(event)
        return events
    
    def _generate_event_data(self, table: str, operation: str) -> Dict[str, Any]:
        if table == 'users':
            return {
                'id': self.random.randint(1, 10000),
                'name': f'User {self.random.randint(1, 1000)}',
                'email': f'user{self.random.randint(1, 1000)}@test.com'
            }
        elif table == 'orders':
            return {
                'id': self.random.randint(1, 10000),
                'user_id': self.random.randint(1, 1000),
                'amount': round(self.random.uniform(10, 500), 2)
            }
        else:
            return {'id': self.random.randint(1, 10000), 'data': 'test'}


class VectorDataGenerator(TestDataGenerator):
    """Generate vector embedding test data."""
    
    def generate(self, count: int, dimensions: int = 128) -> List[Dict[str, Any]]:
        vectors = []
        for i in range(count):
            vector = {
                'id': f'vec_{i}',
                'embedding': [self.random.gauss(0, 1) for _ in range(dimensions)],
                'metadata': {
                    'category': self.random.choice(['text', 'image', 'audio']),
                    'source': f'source_{self.random.randint(1, 10)}'
                }
            }
            vectors.append(vector)
        return vectors


class GeospatialDataGenerator(TestDataGenerator):
    """Generate geospatial point test data."""
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        points = []
        base_locations = [
            (40.7128, -74.0060),
            (34.0522, -118.2437),
            (41.8781, -87.6298),
            (29.7604, -95.3698),
        ]
        
        for i in range(count):
            base = self.random.choice(base_locations)
            point = {
                'id': f'point_{i}',
                'lat': base[0] + self.random.gauss(0, 0.1),
                'lon': base[1] + self.random.gauss(0, 0.1),
                'name': f'Location {i}',
                'type': self.random.choice(['store', 'warehouse', 'office'])
            }
            points.append(point)
        return points


class SQLCommandGenerator(TestDataGenerator):
    """Generate SQL commands for batch testing."""
    
    def generate(self, count: int) -> List[str]:
        commands = []
        tables = ['users', 'orders', 'products']
        
        for i in range(count):
            cmd_type = self.random.choice(['INSERT', 'UPDATE', 'DELETE', 'SELECT'])
            table = self.random.choice(tables)
            
            if cmd_type == 'INSERT':
                cmd = f"INSERT INTO {table} VALUES ({i}, 'data_{i}')"
            elif cmd_type == 'UPDATE':
                cmd = f"UPDATE {table} SET value = {i} WHERE id = {self.random.randint(1, 100)}"
            elif cmd_type == 'DELETE':
                cmd = f"DELETE FROM {table} WHERE id = {self.random.randint(1, 100)}"
            else:
                cmd = f"SELECT * FROM {table} WHERE id = {self.random.randint(1, 100)}"
            
            commands.append(cmd)
        
        return commands


class BatchCommandGenerator(TestDataGenerator):
    """Generate batch command sequences."""
    
    def generate_batch_sequence(self, length: int = 10) -> List[str]:
        """Generate a sequence of batch commands."""
        commands = ['BEGIN BATCH']
        
        for _ in range(length):
            cmd_type = self.random.choice([
                'INSERT', 'UPDATE', 'DELETE', 
                'BACKUP', 'MIGRATE', 'ANALYZE'
            ])
            
            if cmd_type in ['INSERT', 'UPDATE', 'DELETE']:
                table = self.random.choice(['users', 'orders', 'products'])
                if cmd_type == 'INSERT':
                    commands.append(f"{cmd_type} INTO {table} VALUES (1, 'test')")
                else:
                    commands.append(f"{cmd_type} {table} WHERE id = 1")
            elif cmd_type == 'BACKUP':
                commands.append(f"BACKUP db TO backup_{self.random.randint(1, 100)}.json.gz")
            elif cmd_type == 'MIGRATE':
                commands.append("MIGRATE UP")
            else:
                commands.append(f"ANALYZE {self.random.choice(['users', 'orders'])}")
        
        commands.append('COMMIT')
        return commands


def generate_all_test_data(output_dir: str = './test_data', scale: str = 'medium'):
    """Generate comprehensive test data set."""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    scales = {
        'small': 100,
        'medium': 1000,
        'large': 10000,
        'xlarge': 100000
    }
    
    count = scales.get(scale, 1000)
    
    generators = {
        'users': UserDataGenerator(),
        'orders': OrderDataGenerator(),
        'cdc_events': CDCEventGenerator(),
        'vectors': VectorDataGenerator(),
        'geospatial': GeospatialDataGenerator(),
        'sql_commands': SQLCommandGenerator(),
    }
    
    results = {}
    for name, generator in generators.items():
        if name == 'vectors':
            data = generator.generate(count // 10, dimensions=128)
        elif name == 'geospatial':
            data = generator.generate(count // 10)
        else:
            data = generator.generate(count)
        
        filename = os.path.join(output_dir, f'{name}.json')
        with open(filename, 'w') as f:
            json.dump(data, f)
        
        results[name] = len(data)
        print(f"Generated {len(data)} {name} records -> {filename}")
    
    batch_gen = BatchCommandGenerator()
    sequences = [batch_gen.generate_batch_sequence(random.randint(5, 20)) 
                 for _ in range(100)]
    
    batch_file = os.path.join(output_dir, 'batch_sequences.json')
    with open(batch_file, 'w') as f:
        json.dump(sequences, f)
    
    results['batch_sequences'] = len(sequences)
    print(f"Generated {len(sequences)} batch sequences -> {batch_file}")
    
    return results


if __name__ == '__main__':
    import sys
    scale = sys.argv[1] if len(sys.argv) > 1 else 'medium'
    results = generate_all_test_data(scale=scale)
    print(f"\nTotal records generated: {sum(results.values())}")
