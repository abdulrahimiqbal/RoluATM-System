#!/usr/bin/env python3
"""
RoluATM Raspberry Pi Kiosk Server
Handles PIN requests from cloud backend and controls cash dispenser hardware
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import aiohttp
from aiohttp import web
import RPi.GPIO as GPIO
import pygame
from threading import Thread
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/rolu-kiosk.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RoluKiosk:
    def __init__(self):
        # Configuration
        self.CLOUD_API_URL = os.getenv('CLOUD_API_URL', 'https://rolu-atm-nextjs-i8kebj4yf-rolu.vercel.app')
        self.KIOSK_ID = os.getenv('KIOSK_ID', 'kiosk_001')
        self.PORT = int(os.getenv('KIOSK_PORT', '5000'))
        
        # GPIO Pin Configuration
        self.DISPENSER_RELAY_PIN = 18  # GPIO pin for cash dispenser relay
        self.STATUS_LED_PIN = 24       # Status LED (Green = Ready, Red = Error)
        self.BUZZER_PIN = 23           # Buzzer for audio feedback
        
        # State management
        self.active_withdrawals: Dict[str, Dict] = {}
        self.is_dispensing = False
        self.last_heartbeat = datetime.now()
        
        # Initialize hardware
        self.setup_gpio()
        self.setup_display()
        
        logger.info(f"🥧 RoluATM Kiosk {self.KIOSK_ID} initialized")

    def setup_gpio(self):
        """Initialize GPIO pins for hardware control"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup output pins
            GPIO.setup(self.DISPENSER_RELAY_PIN, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.STATUS_LED_PIN, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
            
            # Set status LED to green (ready)
            GPIO.output(self.STATUS_LED_PIN, GPIO.HIGH)
            
            logger.info("✅ GPIO pins initialized successfully")
        except Exception as e:
            logger.error(f"❌ GPIO initialization failed: {e}")

    def setup_display(self):
        """Initialize pygame for display UI"""
        try:
            pygame.init()
            pygame.font.init()
            
            # Set up display (adjust resolution for your screen)
            self.screen = pygame.display.set_mode((800, 480))
            pygame.display.set_caption("RoluATM Kiosk")
            
            # Fonts
            self.font_large = pygame.font.Font(None, 48)
            self.font_medium = pygame.font.Font(None, 36)
            self.font_small = pygame.font.Font(None, 24)
            
            # Colors
            self.BLACK = (0, 0, 0)
            self.WHITE = (255, 255, 255)
            self.GREEN = (0, 255, 0)
            self.RED = (255, 0, 0)
            self.BLUE = (0, 0, 255)
            self.GRAY = (128, 128, 128)
            
            self.show_ready_screen()
            logger.info("✅ Display initialized successfully")
        except Exception as e:
            logger.error(f"❌ Display initialization failed: {e}")

    def show_ready_screen(self):
        """Display ready screen"""
        self.screen.fill(self.WHITE)
        
        # Title
        title = self.font_large.render("RoluATM", True, self.BLUE)
        title_rect = title.get_rect(center=(400, 100))
        self.screen.blit(title, title_rect)
        
        # Status
        status = self.font_medium.render("Ready for Withdrawals", True, self.GREEN)
        status_rect = status.get_rect(center=(400, 200))
        self.screen.blit(status, status_rect)
        
        # Instructions
        instruction = self.font_small.render("Complete your transaction in the World App", True, self.GRAY)
        instruction_rect = instruction.get_rect(center=(400, 300))
        self.screen.blit(instruction, instruction_rect)
        
        # Kiosk ID
        kiosk_id = self.font_small.render(f"Kiosk ID: {self.KIOSK_ID}", True, self.GRAY)
        kiosk_id_rect = kiosk_id.get_rect(center=(400, 400))
        self.screen.blit(kiosk_id, kiosk_id_rect)
        
        pygame.display.flip()

    def show_pin_input_screen(self, withdrawal_id: str, amount: float):
        """Display PIN input screen"""
        self.screen.fill(self.WHITE)
        
        # Title
        title = self.font_large.render("Enter PIN", True, self.BLUE)
        title_rect = title.get_rect(center=(400, 80))
        self.screen.blit(title, title_rect)
        
        # Amount
        amount_text = self.font_medium.render(f"Amount: ${amount:.2f}", True, self.BLACK)
        amount_rect = amount_text.get_rect(center=(400, 140))
        self.screen.blit(amount_text, amount_rect)
        
        # PIN input area
        pin_area = pygame.Rect(250, 200, 300, 60)
        pygame.draw.rect(self.screen, self.GRAY, pin_area, 2)
        
        # Instructions
        instruction = self.font_small.render("Enter the 6-digit PIN from your phone", True, self.GRAY)
        instruction_rect = instruction.get_rect(center=(400, 320))
        self.screen.blit(instruction, instruction_rect)
        
        # Keypad (simple grid)
        self.draw_keypad()
        
        pygame.display.flip()

    def draw_keypad(self):
        """Draw on-screen keypad"""
        keypad_layout = [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            ['*', '0', '#']
        ]
        
        start_x, start_y = 250, 350
        button_size = 80
        gap = 10
        
        for row_idx, row in enumerate(keypad_layout):
            for col_idx, key in enumerate(row):
                x = start_x + col_idx * (button_size + gap)
                y = start_y + row_idx * (button_size + gap)
                
                # Button background
                button_rect = pygame.Rect(x, y, button_size, button_size)
                pygame.draw.rect(self.screen, self.GRAY, button_rect)
                pygame.draw.rect(self.screen, self.BLACK, button_rect, 2)
                
                # Button text
                text = self.font_medium.render(key, True, self.BLACK)
                text_rect = text.get_rect(center=button_rect.center)
                self.screen.blit(text, text_rect)

    def play_sound(self, sound_type: str):
        """Play audio feedback"""
        try:
            if sound_type == "success":
                # Success beep pattern
                for _ in range(2):
                    GPIO.output(self.BUZZER_PIN, GPIO.HIGH)
                    time.sleep(0.1)
                    GPIO.output(self.BUZZER_PIN, GPIO.LOW)
                    time.sleep(0.1)
            elif sound_type == "error":
                # Error beep pattern
                GPIO.output(self.BUZZER_PIN, GPIO.HIGH)
                time.sleep(0.5)
                GPIO.output(self.BUZZER_PIN, GPIO.LOW)
            elif sound_type == "dispensing":
                # Dispensing sound
                for _ in range(5):
                    GPIO.output(self.BUZZER_PIN, GPIO.HIGH)
                    time.sleep(0.05)
                    GPIO.output(self.BUZZER_PIN, GPIO.LOW)
                    time.sleep(0.05)
        except Exception as e:
            logger.error(f"❌ Sound playback error: {e}")

    async def dispense_cash(self, amount: float) -> bool:
        """Control cash dispenser hardware"""
        if self.is_dispensing:
            logger.warning("⚠️ Dispenser already active")
            return False
        
        try:
            self.is_dispensing = True
            logger.info(f"💰 Dispensing ${amount:.2f}")
            
            # Set status LED to red (busy)
            GPIO.output(self.STATUS_LED_PIN, GPIO.LOW)
            
            # Play dispensing sound
            Thread(target=lambda: self.play_sound("dispensing")).start()
            
            # Activate cash dispenser relay
            GPIO.output(self.DISPENSER_RELAY_PIN, GPIO.HIGH)
            
            # Calculate dispense time based on amount (adjust for your hardware)
            # Assuming 1 second per $10 (customize for your dispenser)
            dispense_time = max(2.0, amount / 10.0)
            await asyncio.sleep(dispense_time)
            
            # Deactivate dispenser
            GPIO.output(self.DISPENSER_RELAY_PIN, GPIO.LOW)
            
            # Set status LED back to green (ready)
            GPIO.output(self.STATUS_LED_PIN, GPIO.HIGH)
            
            # Play success sound
            Thread(target=lambda: self.play_sound("success")).start()
            
            logger.info("✅ Cash dispensed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cash dispensing failed: {e}")
            GPIO.output(self.DISPENSER_RELAY_PIN, GPIO.LOW)  # Safety: turn off relay
            GPIO.output(self.STATUS_LED_PIN, GPIO.HIGH)      # Reset status LED
            Thread(target=lambda: self.play_sound("error")).start()
            return False
        finally:
            self.is_dispensing = False

    async def handle_pin_request(self, request):
        """Handle PIN request from cloud backend"""
        try:
            data = await request.json()
            logger.info(f"📥 Received PIN request: {data}")
            
            withdrawal_id = data.get('withdrawalId')
            amount = data.get('amount')
            pin = data.get('pin')
            expires_at = data.get('expiresAt')
            wallet_address = data.get('walletAddress')
            
            if not all([withdrawal_id, amount, pin, expires_at]):
                return web.json_response({'error': 'Missing required fields'}, status=400)
            
            # Store withdrawal info
            self.active_withdrawals[withdrawal_id] = {
                'amount': amount,
                'pin': pin,
                'expires_at': datetime.fromisoformat(expires_at.replace('Z', '+00:00')),
                'wallet_address': wallet_address,
                'created_at': datetime.now()
            }
            
            # Show PIN input screen
            self.show_pin_input_screen(withdrawal_id, amount)
            
            # Start PIN input handler
            asyncio.create_task(self.handle_pin_input(withdrawal_id))
            
            return web.json_response({'success': True, 'message': 'PIN request received'})
            
        except Exception as e:
            logger.error(f"❌ PIN request handling error: {e}")
            return web.json_response({'error': 'Internal server error'}, status=500)

    async def handle_pin_input(self, withdrawal_id: str):
        """Handle PIN input from user"""
        withdrawal = self.active_withdrawals.get(withdrawal_id)
        if not withdrawal:
            return
        
        entered_pin = ""
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            # Check if PIN has expired
            if datetime.now() > withdrawal['expires_at']:
                self.show_error_screen("PIN Expired", "Please start a new transaction")
                await asyncio.sleep(5)
                self.show_ready_screen()
                del self.active_withdrawals[withdrawal_id]
                return
            
            # Simple PIN input simulation (in real implementation, use actual keypad/touchscreen)
            # For demo purposes, we'll auto-accept after 10 seconds
            logger.info(f"🔑 Waiting for PIN input for withdrawal {withdrawal_id}")
            logger.info(f"🔑 Expected PIN: {withdrawal['pin']}")
            
            # Simulate PIN input (replace with actual input handling)
            await asyncio.sleep(10)  # Wait for user input
            
            # For demo, assume PIN is correct
            entered_pin = withdrawal['pin']  # In real implementation, get from keypad
            
            if entered_pin == withdrawal['pin']:
                logger.info("✅ PIN verified successfully")
                
                # Show dispensing screen
                self.show_dispensing_screen(withdrawal['amount'])
                
                # Dispense cash
                success = await self.dispense_cash(withdrawal['amount'])
                
                if success:
                    # Show success screen
                    self.show_success_screen(withdrawal['amount'])
                    
                    # Notify cloud backend
                    await self.notify_cloud_completion(withdrawal_id, True)
                    
                    await asyncio.sleep(5)
                    self.show_ready_screen()
                else:
                    # Show error screen
                    self.show_error_screen("Dispenser Error", "Please contact support")
                    await self.notify_cloud_completion(withdrawal_id, False)
                    await asyncio.sleep(5)
                    self.show_ready_screen()
                
                del self.active_withdrawals[withdrawal_id]
                return
            else:
                attempts += 1
                logger.warning(f"❌ Incorrect PIN attempt {attempts}/{max_attempts}")
                self.show_error_screen("Incorrect PIN", f"Attempts remaining: {max_attempts - attempts}")
                Thread(target=lambda: self.play_sound("error")).start()
                await asyncio.sleep(3)
                
                if attempts < max_attempts:
                    self.show_pin_input_screen(withdrawal_id, withdrawal['amount'])
        
        # Max attempts reached
        self.show_error_screen("Too Many Attempts", "Transaction cancelled")
        await self.notify_cloud_completion(withdrawal_id, False)
        await asyncio.sleep(5)
        self.show_ready_screen()
        del self.active_withdrawals[withdrawal_id]

    def show_dispensing_screen(self, amount: float):
        """Show cash dispensing screen"""
        self.screen.fill(self.WHITE)
        
        title = self.font_large.render("Dispensing Cash...", True, self.BLUE)
        title_rect = title.get_rect(center=(400, 150))
        self.screen.blit(title, title_rect)
        
        amount_text = self.font_medium.render(f"${amount:.2f}", True, self.GREEN)
        amount_rect = amount_text.get_rect(center=(400, 220))
        self.screen.blit(amount_text, amount_rect)
        
        instruction = self.font_small.render("Please wait...", True, self.GRAY)
        instruction_rect = instruction.get_rect(center=(400, 300))
        self.screen.blit(instruction, instruction_rect)
        
        pygame.display.flip()

    def show_success_screen(self, amount: float):
        """Show transaction success screen"""
        self.screen.fill(self.WHITE)
        
        title = self.font_large.render("Transaction Complete!", True, self.GREEN)
        title_rect = title.get_rect(center=(400, 150))
        self.screen.blit(title, title_rect)
        
        amount_text = self.font_medium.render(f"${amount:.2f} dispensed", True, self.BLACK)
        amount_rect = amount_text.get_rect(center=(400, 220))
        self.screen.blit(amount_text, amount_rect)
        
        instruction = self.font_small.render("Thank you for using RoluATM!", True, self.GRAY)
        instruction_rect = instruction.get_rect(center=(400, 300))
        self.screen.blit(instruction, instruction_rect)
        
        pygame.display.flip()

    def show_error_screen(self, title: str, message: str):
        """Show error screen"""
        self.screen.fill(self.WHITE)
        
        error_title = self.font_large.render(title, True, self.RED)
        title_rect = error_title.get_rect(center=(400, 150))
        self.screen.blit(error_title, title_rect)
        
        error_message = self.font_medium.render(message, True, self.BLACK)
        message_rect = error_message.get_rect(center=(400, 220))
        self.screen.blit(error_message, message_rect)
        
        pygame.display.flip()

    async def notify_cloud_completion(self, withdrawal_id: str, success: bool):
        """Notify cloud backend of transaction completion"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'withdrawalId': withdrawal_id,
                    'kioskId': self.KIOSK_ID,
                    'success': success,
                    'timestamp': datetime.now().isoformat()
                }
                
                async with session.post(
                    f"{self.CLOUD_API_URL}/api/kiosk-completion",
                    json=payload,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info("✅ Cloud notification sent successfully")
                    else:
                        logger.error(f"❌ Cloud notification failed: {response.status}")
                        
        except Exception as e:
            logger.error(f"❌ Cloud notification error: {e}")

    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'healthy',
            'kiosk_id': self.KIOSK_ID,
            'timestamp': datetime.now().isoformat(),
            'active_withdrawals': len(self.active_withdrawals),
            'is_dispensing': self.is_dispensing
        })

    def cleanup(self):
        """Cleanup GPIO and pygame resources"""
        try:
            GPIO.cleanup()
            pygame.quit()
            logger.info("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")

    async def start_server(self):
        """Start the kiosk web server"""
        app = web.Application()
        app.router.add_post('/pin-request', self.handle_pin_request)
        app.router.add_get('/health', self.health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.PORT)
        await site.start()
        
        logger.info(f"🚀 Kiosk server started on port {self.PORT}")
        
        try:
            # Keep server running
            while True:
                await asyncio.sleep(1)
                
                # Clean up expired withdrawals
                current_time = datetime.now()
                expired_withdrawals = [
                    wid for wid, w in self.active_withdrawals.items()
                    if current_time > w['expires_at']
                ]
                
                for wid in expired_withdrawals:
                    logger.info(f"🗑️ Cleaning up expired withdrawal: {wid}")
                    del self.active_withdrawals[wid]
                
        except KeyboardInterrupt:
            logger.info("🛑 Server shutdown requested")
        finally:
            self.cleanup()

if __name__ == "__main__":
    kiosk = RoluKiosk()
    try:
        asyncio.run(kiosk.start_server())
    except KeyboardInterrupt:
        logger.info("🛑 Kiosk server stopped")
    finally:
        kiosk.cleanup() 