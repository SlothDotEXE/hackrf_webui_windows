import SoapySDR
import numpy as np
from typing import Optional, List, Dict, Any
import asyncio
import logging
from dataclasses import dataclass

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
        
    async def initialize(self) -> bool:
        """Initialize HackRF device."""
        try:
            results = SoapySDR.Device.enumerate({"driver": "hackrf"})
            if not results:
                logger.error("No HackRF devices found")
                return False
                
            self.device = SoapySDR.Device(dict(driver="hackrf"))
            self.apply_config()
            return True
            
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