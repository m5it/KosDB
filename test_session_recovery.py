"""
Tests for session recovery system.
"""

import unittest
import time
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_recovery import (
    SessionState, SessionSerializer, IntegrityChecker,
    SessionPersistence, SessionRecoveryManager,
    PersistentAuthenticator,
    create_session_recovery
)


class TestSessionState(unittest.TestCase):
    def test_session_creation(self):
        session = SessionState(
            session_id="test-123",
            username="alice",
            current_db="mydb",
            is_admin=False,
            privileges={"mydb": ["SELECT"]},
            created_at=time.time(),
            last_activity=time.time(),
            client_address="127.0.0.1",
            custom_state={}
        )
        
        self.assertEqual(session.session_id, "test-123")
        self.assertEqual(session.username, "alice")
    
    def test_session_expiration(self):
        session = SessionState(
            session_id="test-123",
            username="alice",
            current_db=None,
            is_admin=False,
            privileges={},
            created_at=time.time() - 3600,
            last_activity=time.time() - 3600,
            client_address=None,
            custom_state={}
        )
        
        self.assertTrue(session.is_expired(timeout_seconds=1800))
    
    def test_session_touch(self):
        session = SessionState(
            session_id="test-123",
            username="alice",
            current_db=None,
            is_admin=False,
            privileges={},
            created_at=time.time(),
            last_activity=time.time() - 100,
            client_address=None,
            custom_state={}
        )
        
        old_activity = session.last_activity
        session.touch()
        self.assertGreater(session.last_activity, old_activity)
    
    def test_to_from_dict(self):
        session = SessionState(
            session_id="test-123",
            username="alice",
            current_db="mydb",
            is_admin=True,
            privileges={"*": ["ALL"]},
            created_at=1000.0,
            last_activity=2000.0,
            client_address="127.0.0.1",
            custom_state={"key": "value"}
        )
        
        data = session.to_dict()
        restored = SessionState.from_dict(data)
        
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.username, session.username)
        self.assertEqual(restored.current_db, session.current_db)


class TestSessionSerializer(unittest.TestCase):
    def test_json_serialization(self):
        serializer = SessionSerializer('json')
        data = {"key": "value", "number": 42}
        
        serialized = serializer.serialize(data)
        self.assertIsInstance(serialized, bytes)
        
        restored = serializer.deserialize(serialized)
        self.assertEqual(restored, data)
    
    def test_pickle_serialization(self):
        serializer = SessionSerializer('pickle')
        data = {"key": "value", "number": 42}
        
        serialized = serializer.serialize(data)
        self.assertIsInstance(serialized, bytes)
        
        restored = serializer.deserialize(serialized)
        self.assertEqual(restored, data)


class TestIntegrityChecker(unittest.TestCase):
    def test_checksum_computation(self):
        data = b"test data"
        checksum = IntegrityChecker.compute_checksum(data)
        self.assertEqual(len(checksum), 64)
    
    def test_checksum_verification(self):
        data = b"test data"
        checksum = IntegrityChecker.compute_checksum(data)
        
        self.assertTrue(IntegrityChecker.verify_checksum(data, checksum))
        self.assertFalse(IntegrityChecker.verify_checksum(b"wrong data", checksum))
    
    def test_checksum_dict(self):
        data = {"b": 2, "a": 1}
        checksum1 = IntegrityChecker.compute_checksum_dict(data)
        checksum2 = IntegrityChecker.compute_checksum_dict({"a": 1, "b": 2})
        
        self.assertEqual(checksum1, checksum2)


class TestSessionPersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = './test_sessions'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.persistence = SessionPersistence(self.test_dir)
    
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_write_and_load(self):
        session = SessionState(
            session_id="test-session-123",
            username="bob",
            current_db=None,
            is_admin=False,
            privileges={},
            created_at=time.time(),
            last_activity=time.time(),
            client_address=None,
            custom_state={}
        )
        
        result = self.persistence._write_session_sync(session)
        self.assertTrue(result)
        
        loaded = self.persistence.load_session("test-session-123")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.username, "bob")
    
    def test_list_sessions(self):
        for i in range(3):
            session = SessionState(
                session_id=f"session-{i}",
                username=f"user{i}",
                current_db=None,
                is_admin=False,
                privileges={},
                created_at=time.time(),
                last_activity=time.time(),
                client_address=None,
                custom_state={}
            )
            self.persistence._write_session_sync(session)
        
        sessions = self.persistence.list_sessions()
        self.assertEqual(len(sessions), 3)
    
    def test_delete_session(self):
        session = SessionState(
            session_id="to-delete",
            username="temp",
            current_db=None,
            is_admin=False,
            privileges={},
            created_at=time.time(),
            last_activity=time.time(),
            client_address=None,
            custom_state={}
        )
        
        self.persistence._write_session_sync(session)
        self.assertIsNotNone(self.persistence.load_session("to-delete"))
        
        result = self.persistence.delete_session("to-delete")
        self.assertTrue(result)
        self.assertIsNone(self.persistence.load_session("to-delete"))


class TestSessionRecoveryManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = './test_recovery'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.manager = SessionRecoveryManager(data_dir=self.test_dir)
    
    def tearDown(self):
        self.manager.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_create_and_get_session(self):
        self.manager.start()
        
        session = self.manager.create_session(
            session_id="sess-123",
            username="alice",
            is_admin=False
        )
        
        self.assertIsNotNone(session)
        self.assertEqual(session.username, "alice")
        
        retrieved = self.manager.get_session("sess-123")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.username, "alice")
    
    def test_update_session(self):
        self.manager.start()
        
        self.manager.create_session(
            session_id="sess-456",
            username="bob",
            is_admin=False
        )
        
        result = self.manager.update_session("sess-456", {
            'current_db': 'mydb',
            'custom_state': {'key': 'value'}
        })
        
        self.assertTrue(result)
        
        session = self.manager.get_session("sess-456")
        self.assertEqual(session.current_db, 'mydb')
        self.assertEqual(session.custom_state['key'], 'value')
    
    def test_end_session(self):
        self.manager.start()
        
        self.manager.create_session(
            session_id="sess-end",
            username="charlie",
            is_admin=False
        )
        
        self.assertIsNotNone(self.manager.get_session("sess-end"))
        
        result = self.manager.end_session("sess-end")
        self.assertTrue(result)
        
        self.assertIsNone(self.manager.get_session("sess-end"))
    
    def test_recovery(self):
        self.manager.start()
        
        self.manager.create_session(
            session_id="recover-me",
            username="dave",
            is_admin=True,
            privileges={"*": ["ALL"]}
        )
        
        self.manager._persist_all()
        self.manager.stop()
        
        new_manager = SessionRecoveryManager(data_dir=self.test_dir)
        new_manager.start()
        
        try:
            session = new_manager.get_session("recover-me")
            self.assertIsNotNone(session)
            self.assertEqual(session.username, "dave")
            self.assertTrue(session.is_admin)
        finally:
            new_manager.stop()


class TestPersistentAuthenticator(unittest.TestCase):
    def setUp(self):
        self.test_dir = './test_auth'
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_create_authenticator(self):
        class MockDB:
            def authenticate_user(self, username, password):
                if username == "alice" and password == "secret":
                    return True, False, {"mydb": ["SELECT"]}
                return False, False, {}
            
            def check_privilege(self, username, db, table, priv):
                return True
        
        db = MockDB()
        auth = PersistentAuthenticator(db, data_dir=self.test_dir)
        auth.start()
        
        try:
            success, token, info = auth.authenticate("alice", "secret")
            self.assertTrue(success)
            self.assertIsNotNone(token)
            self.assertEqual(info['username'], 'alice')
            
            self.assertTrue(auth.validate_session(token))
        finally:
            auth.stop()


class TestIntegration(unittest.TestCase):
    def test_full_workflow(self):
        test_dir = './test_integration'
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        
        try:
            manager = create_session_recovery(
                data_dir=test_dir,
                session_timeout=3600
            )
            
            manager.start()
            
            for i in range(5):
                manager.create_session(
                    session_id=f"user{i}",
                    username=f"user{i}",
                    is_admin=(i == 0)
                )
            
            self.assertEqual(manager.get_session_count(), 5)
            
            manager.update_session("user1", {'current_db': 'testdb'})
            
            manager._persist_all()
            manager.stop()
            
            new_manager = create_session_recovery(data_dir=test_dir)
            new_manager.start()
            
            self.assertEqual(new_manager.get_session_count(), 5)
            
            session = new_manager.get_session("user1")
            self.assertIsNotNone(session)
            self.assertEqual(session.current_db, 'testdb')
            
            new_manager.stop()
            
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)


if __name__ == '__main__':
    unittest.main(verbosity=2)
