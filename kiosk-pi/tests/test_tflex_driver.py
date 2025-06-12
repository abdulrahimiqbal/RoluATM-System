"""
Tests for T-Flex Driver

These tests use the real serial port /dev/ttyACM0 when available.
Tests are skipped if hardware is not connected.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import serial

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from tflex_driver import TFlexDriver, TFlexException, TFlexStatus


class TestTFlexDriver:
    """Test T-Flex driver functionality"""
    
    def test_driver_init(self):
        """Test driver initialization"""
        driver = TFlexDriver(port="/dev/ttyACM0", timeout=5)
        assert driver.port == "/dev/ttyACM0"
        assert driver.timeout == 5
        assert driver.max_retries == 3
        assert driver.connection is None
    
    @pytest.mark.skipif(
        not os.path.exists("/dev/ttyACM0"),
        reason="T-Flex hardware not connected at /dev/ttyACM0"
    )
    def test_real_hardware_connection(self):
        """Test connection to real T-Flex hardware"""
        driver = TFlexDriver(port="/dev/ttyACM0")
        
        try:
            driver.connect()
            assert driver.connection is not None
            assert driver.connection.is_open
            
            # Test status query
            status = driver.get_status()
            assert isinstance(status, TFlexStatus)
            
        finally:
            driver.disconnect()
    
    def test_mock_serial_connection_success(self):
        """Test successful connection with mocked serial"""
        mock_serial = MagicMock()
        mock_serial.is_open = True
        
        with patch('tflex_driver.serial.Serial', return_value=mock_serial):
            driver = TFlexDriver(port="/dev/ttyACM0")
            
            # Mock successful status response
            mock_serial.read.side_effect = [b'R', b'E', b'A', b'D', b'Y', b'\r']
            
            driver.connect()
            assert driver.connection == mock_serial
    
    def test_mock_status_parsing(self):
        """Test status response parsing"""
        driver = TFlexDriver(port="/dev/ttyACM0")
        mock_serial = MagicMock()
        mock_serial.is_open = True
        driver.connection = mock_serial
        
        # Test READY status
        mock_serial.read.side_effect = [b'R', b'E', b'A', b'D', b'Y', b'\r']
        status = driver.get_status()
        assert status == TFlexStatus.READY
        
        # Reset mock
        mock_serial.reset_mock()
        
        # Test JAM status
        mock_serial.read.side_effect = [b'J', b'A', b'M', b'\r']
        status = driver.get_status()
        assert status == TFlexStatus.JAM
    
    def test_mock_dispense_invalid_count(self):
        """Test dispensing with invalid coin count"""
        driver = TFlexDriver(port="/dev/ttyACM0")
        
        with pytest.raises(TFlexException) as exc_info:
            driver.dispense_coins(0)
        assert "Invalid coin count" in str(exc_info.value)
        
        with pytest.raises(TFlexException) as exc_info:
            driver.dispense_coins(100)
        assert "Invalid coin count" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__]) 