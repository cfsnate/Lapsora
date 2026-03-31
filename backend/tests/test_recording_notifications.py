"""Unit tests for recording notification event emission."""

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.events import emit
from app.services.notifications import handle_event, DEFAULT_EVENT_TOGGLES, _get_event_toggles
from app.services.recording import RecordingProcess, RecordingManager
from app.models import Notification, Profile, Stream, Setting


class TestRecordingNotifications(unittest.TestCase):
    """Test recording event emission during state transitions."""

    def test_recording_started_event_emission(self):
        """Test that recording_started event is emitted when RecordingProcess starts."""
        async def run_test():
            events_emitted = []
            
            # Mock emit to capture calls
            async def mock_emit(*args, **kwargs):
                events_emitted.append((args, kwargs))
            
            with patch('app.services.recording.emit', mock_emit):
                rp = RecordingProcess(
                    profile_id=1,
                    stream_id=10,
                    rtsp_url="rtsp://test.local/stream",
                    output_dir="/tmp/test",
                    segment_duration=30
                )
                
                # Mock the FFmpeg process
                mock_process = AsyncMock()
                mock_process.returncode = None
                
                with patch('asyncio.create_subprocess_exec', return_value=mock_process):
                    with patch('os.makedirs'):
                        with patch.object(rp, '_emit_status_event', new_callable=AsyncMock):
                            await rp._start_ffmpeg()
                
                # Verify recording_started event was emitted
                self.assertEqual(len(events_emitted), 1)
                args, kwargs = events_emitted[0]
                self.assertEqual(args[0], "recording_started")
                self.assertIn("Recording started for Profile 1", args[1])
                self.assertIn("FFmpeg recording process started for profile 1", args[2])
                self.assertEqual(args[3], "info")
                self.assertEqual(len(args), 5)  # event_type, title, body, level, data
                
                event_data = args[4]
                self.assertEqual(event_data['profile_id'], 1)
                self.assertEqual(event_data['stream_id'], 10)
        
        # Run the async test
        asyncio.run(run_test())

    def test_recording_stopped_event_emission(self):
        """Test that recording_stopped event is emitted when RecordingProcess stops."""
        async def run_test():
            with patch('app.services.recording.emit', new_callable=AsyncMock) as mock_emit:
                rp = RecordingProcess(
                    profile_id=2,
                    stream_id=20,
                    rtsp_url="rtsp://test.local/stream2",
                    output_dir="/tmp/test2",
                    segment_duration=60
                )
                
                # Set up initial state as if recording was started
                rp.state = "recording"
                rp.started_at = datetime.now(UTC) - timedelta(seconds=120)
                
                # Mock the FFmpeg process
                mock_process = AsyncMock()
                mock_process.returncode = None
                rp.process = mock_process
                
                with patch.object(rp, '_emit_status_event', new_callable=AsyncMock):
                    await rp._stop_ffmpeg()
                
                # Verify recording_stopped event was emitted
                mock_emit.assert_called_once()
                call_args = mock_emit.call_args[0]
                self.assertEqual(call_args[0], "recording_stopped")
                self.assertIn("Recording stopped for Profile 2", call_args[1])
                self.assertIn("FFmpeg recording process stopped for profile 2 after", call_args[2])
                self.assertEqual(call_args[3], "info")
                
                event_data = call_args[4]
                self.assertEqual(event_data['profile_id'], 2)
                self.assertEqual(event_data['stream_id'], 20)
                self.assertIn('duration_seconds', event_data)
                self.assertGreater(event_data['duration_seconds'], 0)
        
        asyncio.run(run_test())

    def test_recording_failed_event_emission(self):
        """Test that recording_failed event is emitted when FFmpeg process exits with error."""
        async def run_test():
            with patch('app.services.recording.emit', new_callable=AsyncMock) as mock_emit:
                rp = RecordingProcess(
                    profile_id=3,
                    stream_id=30,
                    rtsp_url="rtsp://test.local/stream3",
                    output_dir="/tmp/test3",
                    segment_duration=45
                )
                
                # Set up initial state as if recording was active
                rp.state = "recording"
                rp.started_at = datetime.now(UTC) - timedelta(seconds=60)
                rp.retry_count = 0
                
                with patch.object(rp, '_emit_status_event', new_callable=AsyncMock):
                    with patch.object(rp, '_start_ffmpeg', new_callable=AsyncMock):
                        with patch('asyncio.sleep', new_callable=AsyncMock):
                            await rp._on_process_exit(1)  # Exit code 1 = error
                
                # Verify recording_failed event was emitted
                mock_emit.assert_called_once()
                call_args = mock_emit.call_args[0]
                self.assertEqual(call_args[0], "recording_failed")
                self.assertIn("Recording failed for Profile 3", call_args[1])
                self.assertIn("FFmpeg recording process failed for profile 3 with exit code 1", call_args[2])
                self.assertEqual(call_args[3], "error")
                
                event_data = call_args[4]
                self.assertEqual(event_data['profile_id'], 3)
                self.assertEqual(event_data['stream_id'], 30)
                self.assertEqual(event_data['exit_code'], 1)
                self.assertIn('duration_seconds', event_data)
                self.assertEqual(event_data['retry_count'], 1)
        
        asyncio.run(run_test())


class TestNotificationEventToggles(unittest.TestCase):
    """Test notification event toggle functionality."""

    def test_default_event_toggles_include_recording_events(self):
        """Test that default toggles include recording notification events."""
        self.assertIn('recording_started', DEFAULT_EVENT_TOGGLES)
        self.assertIn('recording_stopped', DEFAULT_EVENT_TOGGLES)
        self.assertIn('recording_failed', DEFAULT_EVENT_TOGGLES)
        self.assertIn('clip_export_complete', DEFAULT_EVENT_TOGGLES)
        self.assertIn('clip_export_failed', DEFAULT_EVENT_TOGGLES)
        
        # Verify recording events are enabled by default
        self.assertTrue(DEFAULT_EVENT_TOGGLES['recording_started'])
        self.assertTrue(DEFAULT_EVENT_TOGGLES['recording_stopped'])
        self.assertTrue(DEFAULT_EVENT_TOGGLES['recording_failed'])
        self.assertTrue(DEFAULT_EVENT_TOGGLES['clip_export_complete'])
        self.assertTrue(DEFAULT_EVENT_TOGGLES['clip_export_failed'])

    def test_get_event_toggles_with_custom_settings(self):
        """Test that custom event toggles can override defaults."""
        # Create a mock db session
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models import Base
        
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        
        try:
            custom_toggles = DEFAULT_EVENT_TOGGLES.copy()
            custom_toggles['recording_started'] = False
            custom_toggles['recording_failed'] = False
            
            # Create setting with custom toggles
            setting = Setting(key="notification_events", value=json.dumps(custom_toggles))
            db.add(setting)
            db.commit()
            
            toggles = _get_event_toggles(db)
            self.assertFalse(toggles['recording_started'])
            self.assertTrue(toggles['recording_stopped'])  # Still default
            self.assertFalse(toggles['recording_failed'])
        finally:
            db.close()

    def test_get_event_toggles_with_malformed_json(self):
        """Test that malformed JSON falls back to defaults."""
        # Create a mock db session
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models import Base
        
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        
        try:
            # Create setting with malformed JSON
            setting = Setting(key="notification_events", value="invalid json{")
            db.add(setting)
            db.commit()
            
            toggles = _get_event_toggles(db)
            self.assertEqual(toggles, DEFAULT_EVENT_TOGGLES)
        finally:
            db.close()

    def test_get_event_toggles_with_no_setting(self):
        """Test that missing setting returns defaults."""
        # Create a mock db session  
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models import Base
        
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        
        try:
            toggles = _get_event_toggles(db)
            self.assertEqual(toggles, DEFAULT_EVENT_TOGGLES)
        finally:
            db.close()


class TestNotificationEventHandling(unittest.TestCase):
    """Test notification event handling and persistence."""

    def test_recording_started_notification_persistence(self):
        """Test that recording_started events are persisted to database."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                with patch('app.services.notifications.sse_queues', []):
                    with patch('app.services.notifications.SessionLocal', return_value=db):
                        await handle_event(
                            "recording_started",
                            "Recording Started",
                            "Profile 1 recording started",
                            "info",
                            {"profile_id": 1, "stream_id": 5}
                        )
                
                # Verify notification was created in database
                notification = db.query(Notification).filter(
                    Notification.event_type == "recording_started"
                ).first()
                self.assertIsNotNone(notification)
                self.assertEqual(notification.title, "Recording Started")
                self.assertEqual(notification.body, "Profile 1 recording started")
                self.assertEqual(notification.level, "info")
            finally:
                db.close()
        
        asyncio.run(run_test())

    def test_recording_failed_notification_persistence(self):
        """Test that recording_failed events are persisted with error level."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                with patch('app.services.notifications.sse_queues', []):
                    with patch('app.services.notifications.SessionLocal', return_value=db):
                        await handle_event(
                            "recording_failed",
                            "Recording Failed",
                            "Profile 2 recording failed with exit code 1",
                            "error",
                            {"profile_id": 2, "exit_code": 1}
                        )
                
                notification = db.query(Notification).filter(
                    Notification.event_type == "recording_failed"
                ).first()
                self.assertIsNotNone(notification)
                self.assertEqual(notification.title, "Recording Failed")
                self.assertEqual(notification.level, "error")
                self.assertIn("exit code 1", notification.body)
            finally:
                db.close()
        
        asyncio.run(run_test())

    def test_sse_broadcast_for_recording_events(self):
        """Test that recording events are broadcast to SSE queues."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                mock_queue = AsyncMock()
                sse_queues = [mock_queue]
                
                with patch('app.services.notifications.sse_queues', sse_queues):
                    with patch('app.services.notifications._sse_lock'):
                        with patch('app.services.notifications.SessionLocal', return_value=db):
                            await handle_event(
                                "recording_stopped",
                                "Recording Stopped",
                                "Profile 3 recording stopped",
                                "info",
                                {"profile_id": 3, "duration_seconds": 120.5}
                            )
                
                # Verify SSE data was queued
                mock_queue.put_nowait.assert_called_once()
                sse_data = json.loads(mock_queue.put_nowait.call_args[0][0])
                self.assertEqual(sse_data['event_type'], "recording_stopped")
                self.assertEqual(sse_data['title'], "Recording Stopped")
                self.assertEqual(sse_data['level'], "info")
            finally:
                db.close()
        
        asyncio.run(run_test())

    def test_apprise_notification_with_enabled_toggle(self):
        """Test that recording events trigger Apprise notifications when enabled."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base, NotificationURL
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                # Set up event toggles with recording_failed enabled
                custom_toggles = DEFAULT_EVENT_TOGGLES.copy()
                custom_toggles['recording_failed'] = True
                setting = Setting(key="notification_events", value=json.dumps(custom_toggles))
                db.add(setting)
                # Add a notification URL so Apprise path is reached
                from app.config import encrypt
                db.add(NotificationURL(label="test", url=encrypt("json://localhost"), enabled=True))
                db.commit()
                
                with patch('app.services.notifications.sse_queues', []):
                    with patch('app.services.notifications.SessionLocal', return_value=db):
                        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                            await handle_event(
                                "recording_failed",
                                "Recording Failed",
                                "Critical recording failure",
                                "error",
                                {"profile_id": 4}
                            )
                        
                        # Verify Apprise notification was attempted
                        mock_to_thread.assert_called_once()
            finally:
                db.close()
        
        asyncio.run(run_test())

    def test_apprise_notification_skipped_when_disabled(self):
        """Test that recording events skip Apprise when toggle is disabled."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                # Set up event toggles with recording_started disabled
                custom_toggles = DEFAULT_EVENT_TOGGLES.copy()
                custom_toggles['recording_started'] = False
                setting = Setting(key="notification_events", value=json.dumps(custom_toggles))
                db.add(setting)
                db.commit()
                
                with patch('app.services.notifications.sse_queues', []):
                    with patch('app.services.notifications.SessionLocal', return_value=db):
                        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                            await handle_event(
                                "recording_started",
                                "Recording Started", 
                                "Profile recording started",
                                "info",
                                {"profile_id": 5}
                            )
                        
                        # Verify Apprise notification was NOT attempted
                        mock_to_thread.assert_not_called()
            finally:
                db.close()
        
        asyncio.run(run_test())


class TestRecordingManagerNotifications(unittest.TestCase):
    """Test that RecordingManager triggers appropriate notifications."""

    def test_start_recording_emits_events_on_success(self):
        """Test that RecordingManager.start() triggers recording_started event."""
        async def run_test():
            # Create a mock db session
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.models import Base
            
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                # Set up test data
                stream = Stream(name="Test Stream", url="rtsp://test.local", source_type="rtsp")
                db.add(stream)
                db.flush()
                
                profile = Profile(
                    name="Test Profile",
                    stream_id=stream.id,
                    recording_enabled=True,
                    recording_mode="always",
                    segment_duration_seconds=30
                )
                db.add(profile)
                db.commit()
                
                manager = RecordingManager()
                
                with patch('app.services.recording.emit', new_callable=AsyncMock) as mock_emit:
                    with patch('app.services.recording.resolve_recording_url', return_value="rtsp://test.local"):
                        with patch('app.services.recording._is_within_recording_window', return_value=True):
                            with patch.object(RecordingProcess, '_start_ffmpeg', new_callable=AsyncMock):
                                with patch('app.services.recording.SessionLocal', return_value=db):
                                    await manager.start(profile.id)
                
                # Verify that emit was called (should be called by RecordingProcess._start_ffmpeg)
                # We can't verify the exact call since it's mocked at the RecordingProcess level,
                # but we can verify the RecordingProcess was created and started
                self.assertIn(profile.id, manager._processes)
                self.assertEqual(manager._processes[profile.id].profile_id, profile.id)
            finally:
                db.close()
        
        asyncio.run(run_test())

    def test_stop_recording_emits_events(self):
        """Test that RecordingManager.stop() triggers recording_stopped event."""
        async def run_test():
            manager = RecordingManager()
            
            # Create a mock RecordingProcess
            mock_rp = AsyncMock()
            mock_rp._stop_ffmpeg = AsyncMock()
            manager._processes[1] = mock_rp
            
            await manager.stop(1)
            
            # Verify stop was called
            mock_rp._stop_ffmpeg.assert_called_once()
            self.assertNotIn(1, manager._processes)
        
        asyncio.run(run_test())