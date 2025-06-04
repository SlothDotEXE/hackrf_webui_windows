import threading
import asyncio
import SoapySDR
import numpy as np
import logging
import queue
from typing import Optional, Tuple, Any

# Assuming HackRFDevice and DeviceConfig are accessible, e.g., from .device
# This might need adjustment based on your project structure.
# For now, let's assume they will be passed or imported correctly.
from .device import HackRFDevice, DeviceConfig

logger = logging.getLogger(__name__)

INTERNAL_QUEUE_SIZE = 20 # Reduced size to prevent excessive buffering and improve responsiveness

class SDRStreamer:
    def __init__(self, 
                 hackrf_device_instance: HackRFDevice, 
                 output_async_queue: asyncio.Queue, 
                 main_event_loop: asyncio.AbstractEventLoop):
        self.hackrf_dev = hackrf_device_instance
        self.output_queue = output_async_queue # This is the asyncio.Queue for main.py
        self.main_loop = main_event_loop
        
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._current_config: Optional[DeviceConfig] = None
        self._rx_stream: Optional[int] = None

        # Internal thread-safe queue for SDR data before passing to asyncio loop
        self._internal_data_queue: queue.Queue[Tuple[np.ndarray, float, float]] = queue.Queue(maxsize=INTERNAL_QUEUE_SIZE)
        self._data_transfer_task: Optional[asyncio.Task] = None

    def _setup_stream(self) -> bool:
        if not self.hackrf_dev.device or not self._current_config:
            logger.error("SDRStreamer: HackRF device not initialized or no stream config.")
            return False
        
        try:
            logger.info(f"SDRStreamer: Setting up stream. Freq: {self._current_config.center_freq/1e6:.2f}MHz, "
                        f"Rate: {self._current_config.sample_rate/1e6:.2f}Msps, BW: {self._current_config.bandwidth/1e6:.2f}MHz, "
                        f"LNA: {self._current_config.lna_gain}, VGA: {self._current_config.vga_gain}")
            
            self.hackrf_dev.device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, self._current_config.sample_rate)
            self.hackrf_dev.device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, self._current_config.center_freq)
            self.hackrf_dev.device.setBandwidth(SoapySDR.SOAPY_SDR_RX, 0, self._current_config.bandwidth)
            self.hackrf_dev.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", self._current_config.lna_gain)
            self.hackrf_dev.device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", self._current_config.vga_gain)

            self._rx_stream = self.hackrf_dev.device.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32, [0])
            self.hackrf_dev.device.activateStream(self._rx_stream)
            logger.info("SDRStreamer: Stream activated.")
            return True
        except Exception as e:
            logger.error(f"SDRStreamer: Error setting up or activating stream: {e}", exc_info=True)
            if self._rx_stream is not None and self.hackrf_dev.device:
                try: self.hackrf_dev.device.closeStream(self._rx_stream)
                except Exception as e_close: logger.error(f"SDRStreamer: Exception closing stream during setup failure: {e_close}")
            self._rx_stream = None
            return False

    def _close_stream(self):
        if self._rx_stream is not None and self.hackrf_dev.device:
            try: 
                self.hackrf_dev.device.deactivateStream(self._rx_stream)
                logger.info("SDRStreamer: Stream deactivated.")
            except Exception as e: logger.error(f"SDRStreamer: Error deactivating stream: {e}", exc_info=True)
            try: 
                self.hackrf_dev.device.closeStream(self._rx_stream)
                logger.info("SDRStreamer: Stream closed.")
            except Exception as e: logger.error(f"SDRStreamer: Error closing stream: {e}", exc_info=True)
        self._rx_stream = None

    def _run(self):
        logger.info("SDRStreamer data acquisition thread started.")
        
        if not self._current_config:
            logger.error("SDRStreamer: Missing initial stream configuration for _run.")
            self._running = False
            
        if self._running and not self._setup_stream():
            logger.error("SDRStreamer: Failed to setup initial stream in _run.")
            self._running = False

        buffer = np.zeros(self._current_config.buffer_size if self._current_config else 131072, np.complex64)
        
        while self._running:
            try:
                if not self.hackrf_dev.device or self._rx_stream is None:
                    logger.warning("SDRStreamer: Device or stream unavailable in _run. Attempting re-setup.")
                    if not self._setup_stream():
                        logger.error("SDRStreamer: Failed to re-setup stream. Stopping thread after delay.")
                        time.sleep(0.5) # Avoid rapid spin-fail
                        break # Exit acquisition thread
                    else:
                        buffer = np.zeros(self._current_config.buffer_size, np.complex64)

                status = self.hackrf_dev.device.readStream(self._rx_stream, [buffer], len(buffer), timeoutUs=50000) # 0.05s timeout for better responsiveness

                if status.ret > 0:
                    samples_chunk = np.copy(buffer[:status.ret])
                    freq_at_capture = self._current_config.center_freq 
                    sample_rate_at_capture = self._current_config.sample_rate
                    item = (samples_chunk, freq_at_capture, sample_rate_at_capture)
                    try:
                        self._internal_data_queue.put_nowait(item)
                    except queue.Full:
                        logger.warning(f"SDRStreamer: Internal data queue full ({self._internal_data_queue.qsize()}/{INTERNAL_QUEUE_SIZE}). Dropping {len(samples_chunk)} samples.")
                elif status.ret == SoapySDR.SOAPY_SDR_TIMEOUT:
                    logger.debug("SDRStreamer: readStream timeout.")
                elif status.ret == SoapySDR.SOAPY_SDR_OVERFLOW:
                    logger.warning("SDRStreamer: Overflow (O) detected in readStream. Data likely lost at driver/hardware level.")
                else:
                    logger.error(f"SDRStreamer: readStream error: {status.ret} ({SoapySDR.SoapySDR_errToStr(status.ret)}) Attempting to reset stream.")
                    self._close_stream()
                    time.sleep(0.1) # Brief pause before trying to re-setup in next loop iteration
                    
            except Exception as e:
                logger.error(f"SDRStreamer: Unhandled exception in _run loop: {e}", exc_info=True)
                time.sleep(0.5) # Sleep for a bit before trying to continue

        self._close_stream()
        logger.info("SDRStreamer data acquisition thread stopped.")

    async def _transfer_data_to_async_queue(self):
        logger.info("SDRStreamer asyncio data transfer task started.")
        while self._running:
            try:
                item = self._internal_data_queue.get(block=True, timeout=0.05) # Wait up to 50ms for an item
                self._internal_data_queue.task_done() # For queue.join() if ever used
                try:
                    await self.output_queue.put(item)
                except asyncio.QueueFull: # Should not happen if main.py queue has reasonable size and consumer is active
                    logger.warning(f"SDRStreamer: Async output_queue is full. Dropping item. This indicates slow consumer in main.py.")
                except Exception as e_put_async:
                    logger.error(f"SDRStreamer: Error putting to async output_queue: {e_put_async}", exc_info=True)
            except queue.Empty:
                # This is normal if the acquisition thread isn't producing data fast enough or is paused
                if not self._running: break # Exit if stopping
                await asyncio.sleep(0.01) # Small sleep if internal queue is empty but still running
            except Exception as e:
                logger.error(f"SDRStreamer: Unhandled exception in _transfer_data_to_async_queue: {e}", exc_info=True)
                if not self._running: break
                await asyncio.sleep(0.1) # Brief pause after an error
        logger.info("SDRStreamer asyncio data transfer task stopped.")

    def start(self, initial_config: DeviceConfig):
        if self._thread is not None or self._data_transfer_task is not None:
            logger.warning("SDRStreamer: Start called but tasks already exist.")
            return

        logger.info(f"SDRStreamer: Starting with config: Freq {initial_config.center_freq/1e6:.2f} MHz, Rate {initial_config.sample_rate/1e6:.2f} Msps")
        self._current_config = initial_config
        self._running = True
        
        # Clear any stale items from queues before starting
        while not self._internal_data_queue.empty():
            try: self._internal_data_queue.get_nowait()
            except queue.Empty: break
        # output_queue (asyncio) is managed by consumer, usually cleared on new connection in main.py

        self._thread = threading.Thread(target=self._run, daemon=True, name="SDRStreamerAcquisitionThread")
        self._thread.start()
        
        self._data_transfer_task = asyncio.create_task(self._transfer_data_to_async_queue(), name="SDRStreamerAsyncTransferTask")
        logger.info("SDRStreamer: Start method called, acquisition thread and async transfer task starting.")

    async def stop(self):
        logger.info("SDRStreamer: Stop method called.")
        self._running = False

        if self._data_transfer_task is not None:
            logger.info("SDRStreamer: Cancelling async data transfer task...")
            self._data_transfer_task.cancel()
            try:
                await self._data_transfer_task
                logger.info("SDRStreamer: Async data transfer task finished.")
            except asyncio.CancelledError:
                logger.info("SDRStreamer: Async data transfer task was cancelled successfully.")
            except Exception as e_task_join:
                logger.error(f"SDRStreamer: Exception joining async data transfer task: {e_task_join}", exc_info=True)
        self._data_transfer_task = None

        if self._thread is not None:
            logger.info("SDRStreamer: Joining acquisition thread...")
            self._thread.join(timeout=2.0) # Wait for thread to finish
            if self._thread.is_alive():
                logger.warning("SDRStreamer: Acquisition thread did not stop in time.")
        self._thread = None
        
        # Drain internal queue after threads are stopped
        logger.info(f"SDRStreamer: Draining internal queue after stop. Approx {self._internal_data_queue.qsize()} items.")
        while not self._internal_data_queue.empty():
            try: self._internal_data_queue.get_nowait()
            except queue.Empty: break

        logger.info("SDRStreamer: Stop method completed.")

    # For changing frequency during sweep (to be implemented fully later)
    def update_stream_config(self, new_config: DeviceConfig):
        """Update streaming configuration and reconfigure the running stream."""
        logger.info(
            f"SDRStreamer: update_stream_config called. New target freq: {new_config.center_freq/1e6:.2f}MHz"
        )

        self._current_config = new_config

        if not self._running:
            return

        # Restart the stream with the new settings
        self._close_stream()
        self._setup_stream()
