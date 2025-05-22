import SoapySDR
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
import asyncio
import logging
from dataclasses import dataclass
import time
import os
import subprocess

logger = logging.getLogger(__name__)

@dataclass
class DeviceConfig:
    sample_rate: float = 2e6
    center_freq: float = 100e6
    bandwidth: float = 2.5e6
    lna_gain: int = 32
    vga_gain: int = 20
    buffer_size: int = 256 * 1024

class HackRFDevice:
    def __init__(self):
        self.device: Optional[SoapySDR.Device] = None
        self.stream: Optional[SoapySDR.Stream] = None
        self.config = DeviceConfig()
        self.running = False
        self.last_init_attempt = 0
        
    async def check_device_availability(self) -> bool:
        """Check if the HackRF device is available and not in use."""
        try:
            # Use hackrf_info command to check device availability
            process = subprocess.run(
                ["hackrf_info"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                timeout=2
            )
            output = process.stdout.decode('utf-8') + process.stderr.decode('utf-8')
            
            if "Found HackRF" in output and "busy" not in output.lower():
                return True
            else:
                if "busy" in output.lower():
                    logger.error("HackRF device is busy")
                elif "Found HackRF" not in output:
                    logger.error("HackRF device not found")
                return False
        except Exception as e:
            logger.error(f"Error checking HackRF availability: {e}")
            return False
        
    async def reset_device(self) -> bool:
        """Attempt to reset the device if it's in a bad state."""
        try:
            logger.info("Attempting to reset HackRF device...")
            
            # First, try to close any existing connections
            if self.device:
                try:
                    if self.stream:
                        self.device.deactivateStream(self.stream)
                        self.device.closeStream(self.stream)
                        self.stream = None
                except:
                    pass
                self.device = None
            
            # Short delay to allow USB reset
            await asyncio.sleep(0.5)
            
            # Attempt to reset the device
            try:
                subprocess.run(
                    ["hackrf_reset"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    timeout=2
                )
                # Wait for reset to complete
                await asyncio.sleep(1)
                return True
            except:
                logger.error("Failed to reset HackRF device")
                return False
                
        except Exception as e:
            logger.error(f"Error during device reset: {e}")
            return False
        
    async def initialize(self) -> bool:
        """Initialize HackRF device."""
        # Don't attempt to initialize too frequently
        current_time = time.time()
        if current_time - self.last_init_attempt < 2:
            logger.warning("Attempted to initialize device too frequently")
            await asyncio.sleep(2)
        
        self.last_init_attempt = current_time
        
        try:
            # First check if device is available
            if not await self.check_device_availability():
                logger.error("HackRF device is not available or busy")
                return False
            
            # Clean up any existing device instance
            if self.device:
                try:
                    if self.stream:
                        self.device.deactivateStream(self.stream)
                        self.device.closeStream(self.stream)
                        self.stream = None
                except:
                    pass
                self.device = None
            
            results = SoapySDR.Device.enumerate({"driver": "hackrf"})
            if not results:
                logger.error("No HackRF devices found")
                return False
                
            try:
                self.device = SoapySDR.Device(dict(driver="hackrf"))
                self.apply_config()
                logger.info("HackRF device initialized successfully")
                return True
            except Exception as e:
                # Check if this is a resource busy error
                error_str = str(e).lower()
                if "resource busy" in error_str or "device or resource busy" in error_str:
                    logger.error("HackRF device is busy")
                    # Try to reset the device
                    if await self.reset_device():
                        # Try again after reset
                        try:
                            self.device = SoapySDR.Device(dict(driver="hackrf"))
                            self.apply_config()
                            logger.info("HackRF device initialized successfully after reset")
                            return True
                        except Exception as retry_error:
                            logger.error(f"Failed to initialize device after reset: {retry_error}")
                    return False
                else:
                    logger.error(f"Error initializing device: {e}")
                    return False
            
        except Exception as e:
            logger.error(f"Error initializing device: {e}")
            return False
            
    def apply_config(self):
        """Apply current configuration to device."""
        if not self.device:
            return
            
        try:
            self.device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, self.config.sample_rate)
            self.device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, self.config.center_freq)
            self.device.setBandwidth(SoapySDR.SOAPY_SDR_RX, 0, self.config.bandwidth)
            self.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", self.config.lna_gain)
            self.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", self.config.vga_gain)
            
        except Exception as e:
            logger.error(f"Error applying configuration: {e}")
            
    async def start_stream(self) -> bool:
        """Start the RX stream."""
        if not self.device:
            return False
            
        try:
            self.stream = self.device.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)
            self.device.activateStream(self.stream)
            self.running = True
            return True
            
        except Exception as e:
            logger.error(f"Error starting stream: {e}")
            return False
            
    async def stop_stream(self):
        """Stop the RX stream."""
        if self.stream and self.device:
            try:
                self.running = False
                self.device.deactivateStream(self.stream)
                self.device.closeStream(self.stream)
                self.stream = None
                
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
                
    async def read_samples(self) -> np.ndarray:
        """Read a buffer of samples from the device."""
        if not self.stream or not self.device or not self.running:
            return np.array([])
            
        try:
            buffer = np.zeros(self.config.buffer_size, np.complex64)
            status = self.device.readStream(self.stream, [buffer], len(buffer), timeoutUs=1000000)
            
            if status.ret > 0:
                return buffer[:status.ret]
            else:
                return np.array([])
                
        except Exception as e:
            logger.error(f"Error reading samples: {e}")
            return np.array([])
            
    def set_frequency(self, freq: float):
        """Set center frequency."""
        if self.device:
            try:
                self.config.center_freq = freq
                self.device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
            except Exception as e:
                logger.error(f"Error setting frequency: {e}")
                
    def set_sample_rate(self, rate: float):
        """Set sample rate."""
        if self.device:
            try:
                self.config.sample_rate = rate
                self.device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, rate)
            except Exception as e:
                logger.error(f"Error setting sample rate: {e}")
                
    def set_gains(self, lna: int, vga: int):
        """Set LNA and VGA gains."""
        if self.device:
            try:
                self.config.lna_gain = lna
                self.config.vga_gain = vga
                self.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", lna)
                self.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", vga)
            except Exception as e:
                logger.error(f"Error setting gains: {e}")
                
    async def cleanup(self):
        """Clean up device resources."""
        await self.stop_stream()
        self.device = None 