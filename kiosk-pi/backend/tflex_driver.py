"""
Telequip T-Flex Coin Mechanism Driver

Real hardware driver for T-Flex coin mechanism via USB-CDC.
Opens /dev/ttyACM0 at 9600 7E1, sends Dnn\r and S\r commands.
Retries jam/low-coin up to 3 times, then raises 500 error.
"""

import logging
import serial
import time
from typing import Dict, Optional, Tuple
from enum import Enum


class TFlexStatus(Enum):
    """T-Flex status codes"""
    READY = "READY"
    JAM = "JAM"
    LOW_COIN = "LOW_COIN"
    DISPENSING = "DISPENSING"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class TFlexException(Exception):
    """T-Flex hardware exception"""
    pass


class TFlexDriver:
    """
    Telequip T-Flex coin mechanism driver
    
    Protocol:
    - 9600 baud, 7 data bits, even parity, 1 stop bit (7E1)
    - Commands: Dnn\r (dispense nn coins), S\r (status)
    - Responses: ASCII status codes terminated with \r
    """
    
    def __init__(self, port: str = "/dev/ttyACM0", timeout: int = 5):
        self.port = port
        self.timeout = timeout
        self.connection: Optional[serial.Serial] = None
        self.logger = logging.getLogger(__name__)
        self.max_retries = 3
        
    def connect(self) -> None:
        """
        Establish connection to T-Flex mechanism
        Raises TFlexException if connection fails
        """
        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=9600,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            # Wait for device to initialize
            time.sleep(0.5)
            
            # Test connection with status command
            status = self.get_status()
            self.logger.info(f"T-Flex connected on {self.port}, status: {status}")
            
        except serial.SerialException as e:
            raise TFlexException(f"Failed to connect to T-Flex on {self.port}: {e}")
        except Exception as e:
            raise TFlexException(f"T-Flex initialization error: {e}")
    
    def disconnect(self) -> None:
        """Close connection to T-Flex mechanism"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            self.logger.info("T-Flex disconnected")
    
    def _send_command(self, command: str) -> str:
        """
        Send command to T-Flex and read response
        
        Args:
            command: Command string (without \r terminator)
            
        Returns:
            Response string (without \r terminator)
            
        Raises:
            TFlexException: If communication fails
        """
        if not self.connection or not self.connection.is_open:
            raise TFlexException("T-Flex not connected")
        
        try:
            # Send command with \r terminator
            cmd_bytes = (command + "\r").encode('ascii')
            self.connection.write(cmd_bytes)
            self.logger.debug(f"Sent command: {command}")
            
            # Read response until \r
            response = ""
            start_time = time.time()
            
            while True:
                if time.time() - start_time > self.timeout:
                    raise TFlexException(f"Timeout waiting for response to: {command}")
                
                byte = self.connection.read(1)
                if not byte:
                    continue
                    
                char = byte.decode('ascii', errors='ignore')
                if char == '\r':
                    break
                response += char
            
            self.logger.debug(f"Received response: {response}")
            return response.strip()
            
        except serial.SerialException as e:
            raise TFlexException(f"Communication error: {e}")
        except UnicodeDecodeError as e:
            raise TFlexException(f"Invalid response encoding: {e}")
    
    def get_status(self) -> TFlexStatus:
        """
        Get current T-Flex status
        
        Returns:
            TFlexStatus enum value
            
        Raises:
            TFlexException: If communication fails
        """
        try:
            response = self._send_command("S")
            
            # Parse status response
            if "READY" in response.upper():
                return TFlexStatus.READY
            elif "JAM" in response.upper():
                return TFlexStatus.JAM
            elif "LOW" in response.upper() or "EMPTY" in response.upper():
                return TFlexStatus.LOW_COIN
            elif "DISPENSING" in response.upper() or "BUSY" in response.upper():
                return TFlexStatus.DISPENSING
            elif "ERROR" in response.upper():
                return TFlexStatus.ERROR
            else:
                self.logger.warning(f"Unknown status response: {response}")
                return TFlexStatus.ERROR
                
        except TFlexException as e:
            self.logger.error(f"Status check failed: {e}")
            return TFlexStatus.OFFLINE
    
    def dispense_coins(self, count: int) -> bool:
        """
        Dispense specified number of coins
        
        Args:
            count: Number of coins to dispense (1-99)
            
        Returns:
            True if successful, False if failed after retries
            
        Raises:
            TFlexException: If invalid parameters or communication fails
        """
        if not 1 <= count <= 99:
            raise TFlexException(f"Invalid coin count: {count} (must be 1-99)")
        
        command = f"D{count:02d}"
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Dispensing {count} coins (attempt {attempt + 1})")
                
                # Check status before dispensing
                status = self.get_status()
                if status == TFlexStatus.OFFLINE:
                    raise TFlexException("T-Flex is offline")
                elif status in [TFlexStatus.JAM, TFlexStatus.LOW_COIN]:
                    self.logger.warning(f"Status issue before dispense: {status}")
                    if attempt == self.max_retries - 1:
                        raise TFlexException(f"Cannot dispense: {status.value}")
                    time.sleep(2)  # Wait before retry
                    continue
                
                # Send dispense command
                response = self._send_command(command)
                
                # Wait for dispensing to complete
                max_wait = 30  # 30 seconds max dispense time
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    status = self.get_status()
                    
                    if status == TFlexStatus.READY:
                        self.logger.info(f"Successfully dispensed {count} coins")
                        return True
                    elif status == TFlexStatus.DISPENSING:
                        time.sleep(0.5)  # Still dispensing
                        continue
                    elif status in [TFlexStatus.JAM, TFlexStatus.LOW_COIN]:
                        self.logger.warning(f"Dispense failed: {status}")
                        if attempt == self.max_retries - 1:
                            raise TFlexException(f"Dispense failed after {self.max_retries} attempts: {status.value}")
                        break  # Retry
                    else:
                        raise TFlexException(f"Unexpected status during dispense: {status}")
                
                # Timeout waiting for completion
                self.logger.error("Timeout waiting for dispense completion")
                if attempt == self.max_retries - 1:
                    raise TFlexException("Dispense timeout after retries")
                
            except TFlexException as e:
                if attempt == self.max_retries - 1:
                    raise  # Re-raise on final attempt
                self.logger.warning(f"Dispense attempt {attempt + 1} failed: {e}")
                time.sleep(2)  # Wait before retry
        
        return False
    
    def get_coin_count(self) -> int:
        """
        Get current coin count in mechanism
        
        Returns:
            Number of coins available, or 0 if unknown
        """
        try:
            # T-Flex may not support coin count query
            # This is a placeholder for future firmware support
            response = self._send_command("C")
            
            # Try to parse numeric response
            try:
                return int(response)
            except ValueError:
                self.logger.warning(f"Non-numeric coin count response: {response}")
                return 0
                
        except TFlexException as e:
            self.logger.error(f"Coin count query failed: {e}")
            return 0
    
    def is_connected(self) -> bool:
        """Check if T-Flex is connected and responsive"""
        try:
            status = self.get_status()
            return status != TFlexStatus.OFFLINE
        except Exception:
            return False
    
    def get_diagnostics(self) -> Dict[str, any]:
        """
        Get diagnostic information
        
        Returns:
            Dictionary with diagnostic data
        """
        diagnostics = {
            "port": self.port,
            "connected": self.is_connected(),
            "status": "unknown",
            "coin_count": 0,
            "last_error": None
        }
        
        try:
            status = self.get_status()
            diagnostics["status"] = status.value
            
            if status != TFlexStatus.OFFLINE:
                diagnostics["coin_count"] = self.get_coin_count()
                
        except Exception as e:
            diagnostics["last_error"] = str(e)
        
        return diagnostics 