"""
RoluATM Kiosk Backend - Flask Application

Main Flask app with T-Flex driver integration, Prometheus metrics,
and cloud API connectivity. Fails loudly if hardware or cloud unavailable.
"""

import os
import logging
import time
from typing import Dict, Optional
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import requests
from dotenv import load_dotenv

from tflex_driver import TFlexDriver, TFlexException, TFlexStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', '/tmp/roluatm.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Flask app configuration
app = Flask(__name__)
CORS(app)

# Configuration from environment
CLOUD_API_URL = os.getenv('CLOUD_API_URL')
KIOSK_ID = os.getenv('KIOSK_ID', 'kiosk-001')
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyACM0')
OFFLINE_TIMEOUT = int(os.getenv('OFFLINE_TIMEOUT', '10'))

if not CLOUD_API_URL:
    raise ValueError("CLOUD_API_URL environment variable required")

# Global hardware driver
tflex_driver: Optional[TFlexDriver] = None

# Prometheus metrics
REQUEST_COUNT = Counter('roluatm_requests_total', 'Total requests', ['endpoint', 'method', 'status'])
REQUEST_DURATION = Histogram('roluatm_request_duration_seconds', 'Request duration', ['endpoint'])
COIN_DISPENSES = Counter('roluatm_coins_dispensed_total', 'Total coins dispensed')
HARDWARE_STATUS = Gauge('roluatm_hardware_status', 'Hardware status (1=ok, 0=error)')
CLOUD_STATUS = Gauge('roluatm_cloud_status', 'Cloud API status (1=ok, 0=error)')
LAST_CLOUD_CHECK = Gauge('roluatm_last_cloud_check_timestamp', 'Last cloud check timestamp')

# Cloud connectivity state
cloud_last_check: Optional[datetime] = None
cloud_is_online: bool = False


def init_hardware() -> None:
    """Initialize T-Flex hardware connection"""
    global tflex_driver
    
    try:
        tflex_driver = TFlexDriver(port=SERIAL_PORT)
        tflex_driver.connect()
        HARDWARE_STATUS.set(1)
        logger.info("T-Flex hardware initialized successfully")
    except TFlexException as e:
        logger.error(f"Failed to initialize T-Flex hardware: {e}")
        HARDWARE_STATUS.set(0)
        raise


def check_cloud_connectivity() -> bool:
    """
    Check cloud API connectivity
    
    Returns:
        True if cloud is reachable, False otherwise
    """
    global cloud_last_check, cloud_is_online
    
    try:
        response = requests.get(
            f"{CLOUD_API_URL}/health",
            timeout=5,
            headers={'User-Agent': f'RoluATM-Kiosk/{KIOSK_ID}'}
        )
        
        if response.status_code == 200:
            cloud_is_online = True
            CLOUD_STATUS.set(1)
            logger.debug("Cloud API is online")
        else:
            cloud_is_online = False
            CLOUD_STATUS.set(0)
            logger.warning(f"Cloud API returned status {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        cloud_is_online = False
        CLOUD_STATUS.set(0)
        logger.error(f"Cloud API connectivity check failed: {e}")
    
    cloud_last_check = datetime.now()
    LAST_CLOUD_CHECK.set(cloud_last_check.timestamp())
    return cloud_is_online


def is_cloud_offline() -> bool:
    """
    Check if cloud has been offline too long
    
    Returns:
        True if cloud is considered offline
    """
    global cloud_last_check, cloud_is_online
    
    # Check if we need to test connectivity
    if (cloud_last_check is None or 
        datetime.now() - cloud_last_check > timedelta(seconds=5)):
        check_cloud_connectivity()
    
    # Consider offline if last successful check was too long ago
    if not cloud_is_online and cloud_last_check:
        offline_duration = datetime.now() - cloud_last_check
        return offline_duration.total_seconds() > OFFLINE_TIMEOUT
    
    return not cloud_is_online


@app.before_request
def before_request():
    """Record request metrics"""
    request.start_time = time.time()


@app.after_request
def after_request(response):
    """Record response metrics"""
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        endpoint = request.endpoint or 'unknown'
        REQUEST_DURATION.labels(endpoint=endpoint).observe(duration)
        REQUEST_COUNT.labels(
            endpoint=endpoint,
            method=request.method,
            status=response.status_code
        ).inc()
    return response


@app.errorhandler(TFlexException)
def handle_tflex_error(error):
    """Handle T-Flex hardware errors"""
    logger.error(f"T-Flex error: {error}")
    HARDWARE_STATUS.set(0)
    return jsonify({
        'error': 'Hardware error',
        'message': str(error),
        'type': 'hardware'
    }), 500


@app.errorhandler(requests.exceptions.RequestException)
def handle_cloud_error(error):
    """Handle cloud API errors"""
    logger.error(f"Cloud API error: {error}")
    CLOUD_STATUS.set(0)
    return jsonify({
        'error': 'Cloud service unavailable',
        'message': str(error),
        'type': 'cloud'
    }), 503


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    
    # Check hardware status
    hardware_ok = tflex_driver and tflex_driver.is_connected()
    HARDWARE_STATUS.set(1 if hardware_ok else 0)
    
    # Check cloud status
    cloud_ok = check_cloud_connectivity()
    
    status = {
        'kiosk_id': KIOSK_ID,
        'timestamp': datetime.now().isoformat(),
        'hardware': {
            'tflex_connected': hardware_ok,
            'port': SERIAL_PORT,
            'status': tflex_driver.get_status().value if tflex_driver else 'disconnected'
        },
        'cloud': {
            'api_url': CLOUD_API_URL,
            'online': cloud_ok,
            'last_check': cloud_last_check.isoformat() if cloud_last_check else None
        },
        'overall_status': 'healthy' if (hardware_ok and cloud_ok) else 'degraded'
    }
    
    if hardware_ok and tflex_driver:
        status['hardware'].update(tflex_driver.get_diagnostics())
    
    return jsonify(status), 200 if (hardware_ok and cloud_ok) else 503


@app.route('/api/balance', methods=['GET'])
def get_balance():
    """
    Get current coin balance in mechanism
    Fails if hardware unavailable
    """
    
    if not tflex_driver:
        raise TFlexException("T-Flex driver not initialized")
    
    if not tflex_driver.is_connected():
        raise TFlexException("T-Flex not connected")
    
    try:
        status = tflex_driver.get_status()
        coin_count = tflex_driver.get_coin_count()
        
        response = {
            'kiosk_id': KIOSK_ID,
            'timestamp': datetime.now().isoformat(),
            'status': status.value,
            'coin_count': coin_count,
            'available': status == TFlexStatus.READY,
            'quarter_value_usd': coin_count * 0.25
        }
        
        return jsonify(response)
        
    except TFlexException as e:
        logger.error(f"Balance check failed: {e}")
        raise


@app.route('/api/withdraw', methods=['POST'])
def withdraw_coins():
    """
    Withdraw coins from mechanism
    Requires cloud connectivity and hardware availability
    """
    
    # Check cloud connectivity first
    if is_cloud_offline():
        return jsonify({
            'error': 'Service offline',
            'message': 'Please try again later',
            'type': 'offline'
        }), 503
    
    if not tflex_driver:
        raise TFlexException("T-Flex driver not initialized")
    
    if not tflex_driver.is_connected():
        raise TFlexException("T-Flex not connected")
    
    # Parse request
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    amount_usd = data.get('amount_usd')
    session_id = data.get('session_id')
    
    if not amount_usd or not session_id:
        return jsonify({
            'error': 'Missing required fields',
            'required': ['amount_usd', 'session_id']
        }), 400
    
    # Calculate coins needed (quarters = amount * 4)
    coins_needed = int(amount_usd * 4)
    
    if coins_needed <= 0 or coins_needed > 99:
        return jsonify({
            'error': 'Invalid amount',
            'message': 'Amount must result in 1-99 quarters'
        }), 400
    
    try:
        # Verify with cloud API first
        cloud_response = requests.post(
            f"{CLOUD_API_URL}/verify-withdrawal",
            json={
                'kiosk_id': KIOSK_ID,
                'session_id': session_id,
                'amount_usd': amount_usd,
                'coins_needed': coins_needed
            },
            timeout=10,
            headers={'User-Agent': f'RoluATM-Kiosk/{KIOSK_ID}'}
        )
        
        if cloud_response.status_code != 200:
            return jsonify({
                'error': 'Withdrawal not authorized',
                'message': 'Please verify your transaction'
            }), 400
        
        # Dispense coins
        success = tflex_driver.dispense_coins(coins_needed)
        
        if success:
            COIN_DISPENSES.inc(coins_needed)
            
            # Notify cloud of successful dispensing
            try:
                requests.post(
                    f"{CLOUD_API_URL}/confirm-withdrawal",
                    json={
                        'kiosk_id': KIOSK_ID,
                        'session_id': session_id,
                        'coins_dispensed': coins_needed,
                        'timestamp': datetime.now().isoformat()
                    },
                    timeout=5,
                    headers={'User-Agent': f'RoluATM-Kiosk/{KIOSK_ID}'}
                )
            except Exception as e:
                logger.warning(f"Failed to confirm withdrawal with cloud: {e}")
            
            return jsonify({
                'success': True,
                'coins_dispensed': coins_needed,
                'amount_usd': amount_usd,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'error': 'Dispense failed',
                'message': 'Please contact support'
            }), 500
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Cloud API error during withdrawal: {e}")
        return jsonify({
            'error': 'Service temporarily unavailable',
            'message': 'Please try again later'
        }), 503
    except TFlexException as e:
        logger.error(f"Hardware error during withdrawal: {e}")
        raise


@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/', methods=['GET'])
def root():
    """Root endpoint - basic info"""
    return jsonify({
        'service': 'RoluATM Kiosk Backend',
        'kiosk_id': KIOSK_ID,
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })


def create_app():
    """Application factory"""
    return app


if __name__ == '__main__':
    try:
        # Initialize hardware
        init_hardware()
        
        # Initial cloud connectivity check
        check_cloud_connectivity()
        
        # Start Flask app
        port = int(os.getenv('FLASK_PORT', '5000'))
        
        logger.info(f"Starting RoluATM Kiosk Backend on port {port}")
        logger.info(f"Kiosk ID: {KIOSK_ID}")
        logger.info(f"Cloud API: {CLOUD_API_URL}")
        logger.info(f"Serial Port: {SERIAL_PORT}")
        
        app.run(
            host='0.0.0.0',
            port=port,
            debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
        )
        
    except Exception as e:
        logger.critical(f"Failed to start application: {e}")
        raise
    finally:
        # Cleanup hardware connection
        if tflex_driver:
            tflex_driver.disconnect() 