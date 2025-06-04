from fastapi import FastAPI, WebSocket, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import SoapySDR
import numpy as np
from typing import List, Optional, Dict
import asyncio
import json
from dataclasses import dataclass, asdict
import logging
from datetime import datetime
from scipy import signal
from .dsp import SignalProcessor
import time
from .device import HackRFDevice, DeviceConfig
from starlette.websockets import WebSocketDisconnect
from .sdr_streamer import SDRStreamer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HackRF WebUI")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
hackrf = HackRFDevice()
sweep_task: Optional[asyncio.Task] = None
is_sweeping = False
current_sweep_config = {
    "start_freq": 88e6,
    "stop_freq": 108e6,
    "step_size": 20e6,
    "current_freq": 88e6,
    "sample_rate": 20e6,
    "last_update": None,
    "dwell_time": 0.5
}

# Add SignalProcessor instance to global state
signal_processor = SignalProcessor(sample_rate=current_sweep_config["sample_rate"])

@dataclass
class DeviceInfo:
    serial: str
    driver: str
    label: str
    available: bool

def get_hackrf_devices() -> List[DeviceInfo]:
    """List all available HackRF devices."""
    devices = []
    try:
        results = SoapySDR.Device.enumerate({"driver": "hackrf"})
        for result in results:
            # Convert SoapySDRKwargs to dict safely
            result_dict = {}
            if hasattr(result, 'keys'): # Check if it's a dict-like object
                result_dict = {key: result[key] for key in result.keys()}
            elif isinstance(result, dict):
                result_dict = result
            else:
                logger.warning(f"Unexpected device result format: {result}")
                # Attempt to proceed with common keys if possible, or skip
                # For now, we'll try to get serial, driver, label if they exist as attributes
                # This part might need adjustment based on actual SoapySDR behavior for non-dict results
                pass # Or handle more gracefully if possible

            device_info = DeviceInfo(
                serial=result_dict.get("serial", "Unknown"),
                driver=result_dict.get("driver", "hackrf"),
                label=result_dict.get("label", "HackRF One"),
                available=True
            )
            devices.append(device_info)
            logger.info(f"Found HackRF device: {device_info}")
    except Exception as e:
        logger.error(f"Error enumerating devices: {e}")
        # Try direct device creation as fallback
        try:
            device = SoapySDR.Device(dict(driver="hackrf"))
            if device:
                device_info = DeviceInfo(
                    serial="Unknown",
                    driver="hackrf",
                    label="HackRF One",
                    available=True
                )
                devices.append(device_info)
                logger.info("Found HackRF device through direct initialization")
        except Exception as direct_error:
            logger.error(f"Direct device creation also failed: {direct_error}")
    return devices

async def configure_device_for_frequency(freq: float, bandwidth: float = 20e6):
    """Configure device for a specific frequency."""
    if not hackrf.device:
        logger.warning("configure_device_for_frequency: No hackrf.device available")
        return False
    
    try:
        # This function now only updates the *shared* hackrf.config state.
        # The SDRStreamer thread will be responsible for applying this to the hardware.
        hackrf.config.center_freq = freq
        hackrf.config.sample_rate = min(current_sweep_config.get("sample_rate", 20e6), bandwidth)
        hackrf.config.bandwidth = bandwidth
        
        logger.info(f"Global hackrf.config updated: Freq={freq/1e6:.2f}MHz, Rate={hackrf.config.sample_rate/1e6:.2f}MHz")
        # The actual hardware calls (setFrequency, etc.) are now done by SDRStreamer
        # hackrf.apply_config() # This should not be called here anymore for non-streamer contexts
        return True
    except Exception as e:
        logger.error(f"Error updating global hackrf.config: {e}")
        return False

async def sweep_frequency():
    """Sweep through frequencies in steps."""
    logger.warning("Sweep_frequency task started but sweep is currently disabled for SDRStreamer integration.")
    global is_sweeping
    while is_sweeping:
        logger.info("Sweep active (but disabled). Sleeping...")
        await asyncio.sleep(1) # Sleep while "sweeping" (disabled)
    logger.info("Sweep_frequency task ended (sweep was disabled).")

@app.post("/api/sweep/start")
async def start_sweep(
    start_freq: float = Body(...),
    stop_freq: float = Body(...),
    sample_rate: float = Body(default=20e6)
):
    """Start spectrum sweep."""
    global sweep_task, is_sweeping, current_sweep_config
    
    logger.info("SWEEP START ENDPOINT CALLED - NOTE: Full sweep temporarily disabled for SDRStreamer testing.")
    logger.info(f"Requested sweep from {start_freq/1e6:.2f}MHz to {stop_freq/1e6:.2f}MHz. Fixed frequency streaming will use start_freq.")

    if is_sweeping: # Technically, is_sweeping will control the streamer thread now.
        raise HTTPException(status_code=400, detail="Streaming already in progress (or sweep task active but disabled)")
    
    try:
        # Validate frequency range
        if start_freq >= stop_freq:
            raise HTTPException(status_code=400, detail="Start frequency must be less than stop frequency")
        
        if not hackrf.device:
            devices = get_hackrf_devices()
            logger.info(f"Found devices: {devices}")
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            try:
                logger.info("Initializing HackRF device for streaming... {devices}")
                success = await hackrf.initialize()
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to initialize HackRF device")
                logger.info("HackRF device initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize device: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to initialize device: {str(e)}")
        
        # Configure sweep parameters
        current_sweep_config.update({
            "start_freq": start_freq,
            "stop_freq": stop_freq,
            "current_freq": start_freq, # SDRStreamer will use this as its initial fixed frequency
            "sample_rate": sample_rate,
            "step_size": 20e6,
            "last_update": None,
            "dwell_time": 0.5 # Increased from 0.25 to 0.5 seconds
        })
        
        logger.info("Configuring initial frequency before starting sweep task...")
        if not await configure_device_for_frequency(start_freq):
            raise HTTPException(status_code=500, detail="Failed to configure initial frequency")
        
        is_sweeping = True # This flag will signal WebSocket to start/stop its streamer.
        # sweep_task = asyncio.create_task(sweep_frequency()) # Sweep task disabled for now

        return {"status": "success", "message": "Streaming (fixed frequency) initiated. Full sweep disabled."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error starting sweep/stream: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/sweep/stop")
async def stop_sweep():
    """Stop spectrum sweep."""
    global sweep_task, is_sweeping
    
    logger.info("SWEEP STOP ENDPOINT CALLED - This will stop any active SDRStreamer instances via WebSocket logic.")

    if not is_sweeping:
        # If we want to be very robust, we could also try to find active streamer instances here, but
        # the primary control is via is_sweeping flag which websockets should respect.
        raise HTTPException(status_code=400, detail="Streaming not in progress (or sweep was disabled)")
    
    is_sweeping = False # Signal to WebSockets to stop their streamers
    
    # if sweep_task: # Sweep task disabled
    #     try:
    #         sweep_task.cancel()
    #     except asyncio.CancelledError:
    #         logger.info("Sweep task cancelled by stop_sweep.")
    #     except Exception as e_cancel:
    #         logger.error(f"Error cancelling sweep_task: {e_cancel}")
    #     sweep_task = None
            
    return {"status": "success", "message": "Streaming stop signal sent. Full sweep was disabled."}

@app.websocket("/ws/spectrum")
async def websocket_spectrum(websocket: WebSocket):
    """WebSocket endpoint for streaming spectrum data."""
    global is_sweeping, current_sweep_config, hackrf, signal_processor
    
    await websocket.accept()
    logger.info("WebSocket connection accepted. Waiting for is_sweeping to be true to start streamer.")

    sdr_streamer: Optional[SDRStreamer] = None
    sample_queue = asyncio.Queue(maxsize=20) # Queue for (samples, freq, rate) tuples from streamer
    
    try:
        # Wait until sweep/streaming is actually started via HTTP endpoint
        while not is_sweeping:
            await asyncio.sleep(0.5)
            # Check if client disconnected while waiting
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01) 
            except asyncio.TimeoutError:
                pass # No message, continue waiting
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected while waiting for sweep to start.")
                return # Exit if client disconnects

        logger.info("is_sweeping is true, proceeding to initialize SDRStreamer.")

        if not hackrf.device:
            logger.error("HackRF device not available when WebSocket tries to start streamer.")
            await websocket.send_json({"type": "error", "message": "HackRF not initialized or unavailable."})
            return

        # Create and start the SDRStreamer for this WebSocket connection
        # Calculate center frequency to cover the full sweep range
        start_freq = current_sweep_config["start_freq"]
        stop_freq = current_sweep_config["stop_freq"]
        center_freq = (start_freq + stop_freq) / 2  # Center of the sweep range
        bandwidth = min(current_sweep_config["sample_rate"], stop_freq - start_freq + 10e6)  # Add some margin
        
        streamer_config = DeviceConfig(
            sample_rate=current_sweep_config["sample_rate"],
            center_freq=center_freq,  # Use calculated center frequency
            bandwidth=bandwidth,  # Use calculated bandwidth
            lna_gain=hackrf.config.lna_gain, # Get current gains from global HackRFDevice config
            vga_gain=hackrf.config.vga_gain,
            buffer_size=hackrf.config.buffer_size # Use buffer size from global config
        )

        loop = asyncio.get_event_loop()
        sdr_streamer = SDRStreamer(hackrf, sample_queue, loop)
        sdr_streamer.start(initial_config=streamer_config)
        logger.info(f"SDRStreamer started for WebSocket, center freq: {streamer_config.center_freq/1e6:.2f} MHz, covering {start_freq/1e6:.2f}-{stop_freq/1e6:.2f} MHz")

        while is_sweeping: # Loop as long as global sweep flag is true
            try:
                raw_samples, capture_freq, capture_rate = await asyncio.wait_for(sample_queue.get(), timeout=1.0)
                sample_queue.task_done()

                logger.debug(f"WS: Got {len(raw_samples)} samples from queue. Freq: {capture_freq/1e6:.2f}MHz, Rate: {capture_rate/1e6:.2f}Msps")

                # Process samples (FFT, etc.) - optimized for speed
                # Ensure signal_processor's sample rate matches if it changed
                if signal_processor.sample_rate != capture_rate:
                    logger.info(f"Updating signal_processor sample rate to {capture_rate/1e6:.2f}Msps")
                    signal_processor.sample_rate = capture_rate 
                    # Re-create filters if necessary, or ensure SignalProcessor handles this
                
                # Pre-decimate before windowing and FFT to reduce computation
                pre_decimation = 4 # Reduce samples before heavy processing
                samples_decimated = raw_samples[::pre_decimation]
                
                windowed = samples_decimated * signal.windows.blackman(len(samples_decimated))
                spectrum = np.fft.fftshift(np.fft.fft(windowed))
                power_db = 20 * np.log10(np.abs(spectrum) + 1e-10)
                power_db = np.clip(power_db, -100, 0)
                
                final_decimation = 4 # Further decimation on already processed data for final output
                power_db_decimated = power_db[::final_decimation]
                
                num_points = len(power_db_decimated)
                # Use original sample rate for frequency range to show full bandwidth
                # The decimation is just for reducing data points, not changing the frequency range
                freqs = np.linspace(
                    capture_freq - (capture_rate / 2),
                    capture_freq + (capture_rate / 2),
                    num_points
                ).tolist()
                magnitudes = power_db_decimated.tolist()
                
                await websocket.send_json({
                    "type": "spectrum",
                    "frequencies": freqs,
                    "magnitudes": magnitudes,
                    "timestamp": int(time.time() * 1000),
                    "center_freq": capture_freq 
                })
                logger.info(f"WS: Sent {num_points} spectrum points for {capture_freq/1e6:.2f} MHz")

            except asyncio.TimeoutError:
                logger.debug("WS: Timeout getting samples from queue. Checking is_sweeping flag.")
                if not is_sweeping:
                    logger.info("WS: is_sweeping is false, breaking from sample processing loop.")
                    break # Exit loop if sweep stopped
                continue # Continue if still sweeping but queue was empty
            except WebSocketDisconnect:
                logger.info("WS: WebSocket disconnected by client during streaming.")
                is_sweeping = False # Stop streaming if client disconnects
                break
            except Exception as e:
                logger.error(f"WS: Error processing or sending spectrum data: {e}", exc_info=True)
                # Maybe send an error to client, then break or continue carefully
                await asyncio.sleep(0.1) # Small delay after error

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected (outer).")
    except Exception as e_outer:
        logger.error(f"Outer WebSocket error: {e_outer}", exc_info=True)
    finally:
        logger.info("WebSocket connection closing. Stopping SDRStreamer if active.")
        if sdr_streamer:
            await sdr_streamer.stop()
        # is_sweeping = False # Ensure is_sweeping is false if this WebSocket initiated it (more complex logic needed for multi-client)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WebSocket connection resources cleaned up.")


@app.websocket("/ws/hackrf_sweep")
async def websocket_hackrf_sweep(websocket: WebSocket, start_freq: float, stop_freq: float, bin_width: int = 2000000):
    """Run hackrf_sweep and stream results over the WebSocket."""
    await websocket.accept()

    cmd = [
        "hackrf_sweep",
        "-1",
        "-f",
        f"{start_freq/1e6}:{stop_freq/1e6}",
        "-w",
        str(bin_width),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        assert process.stdout is not None
        async for raw in process.stdout:
            line = raw.decode().strip()
            parts = line.split(",")
            if len(parts) < 7:
                continue

            try:
                hz_low = float(parts[2])
                bin_w = float(parts[4])
                db_values = [float(x) for x in parts[6:]]
                freqs = [hz_low + i * bin_w for i in range(len(db_values))]
            except Exception as e:
                logger.error(f"Failed to parse sweep line: {e}")
                continue

            await websocket.send_json(
                {
                    "type": "spectrum",
                    "frequencies": freqs,
                    "magnitudes": db_values,
                    "timestamp": int(time.time() * 1000),
                    "center_freq": hz_low + (bin_w * len(db_values) / 2),
                }
            )
    except WebSocketDisconnect:
        logger.info("hackrf_sweep WebSocket disconnected by client.")
    except Exception as e:
        logger.error(f"hackrf_sweep error: {e}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()

@app.post("/api/tune")
async def tune_frequency(freq: float, sample_rate: float = 2e6):
    """Tune to a specific frequency for FM demodulation."""
    logger.warning("Tune endpoint called - currently has no effect with SDRStreamer architecture.")
    # This endpoint would need to interact with the SDRStreamer's command queue in the new architecture.
    # For now, it does nothing to the active streamer.
    if is_sweeping:
        # await stop_sweep() # Or signal streamer to change frequency
        logger.info("Tune called while streaming is active. Streamer frequency NOT changed by this call yet.")
        pass 

    # Update the global config, which might be picked up if a streamer is restarted.
    hackrf.config.sample_rate = sample_rate
    hackrf.config.center_freq = freq
    # hackrf.apply_config() # This doesn't apply to active streamer directly
    
    return {"status": "warning", "message": f"Tune attempt to {freq/1e6:.2f} MHz. Streamer not directly affected in this version."}

@app.post("/api/gains")
async def set_gains(gains: Dict[str, int] = Body(...)):
    """Set device gain values."""
    logger.info(f"Setting gains via API: {gains}")
    if not hackrf.device:
        raise HTTPException(status_code=400, detail="No active device to set gains on (HackRF not initialized)")
            
    if "LNA" in gains:
        hackrf.config.lna_gain = gains["LNA"]
    if "VGA" in gains:
        hackrf.config.vga_gain = gains["VGA"]
    
    # The SDRStreamer or HackRFDevice needs a way to re-apply these if a stream is active.
    # For now, this updates hackrf.config. The streamer reads this upon its start.
    # If a streamer is active, it won't see this change until it restarts or re-reads config (not implemented yet).
    logger.info(f"Global hackrf.config gains updated: LNA={hackrf.config.lna_gain}, VGA={hackrf.config.vga_gain}")
    # To apply to an active stream, SDRStreamer would need a 'set_gains' command.
    # hackrf.set_gains(hackrf.config.lna_gain, hackrf.config.vga_gain) # This direct call might conflict with streamer

    current_gains = {
        "LNA": hackrf.config.lna_gain,
        "VGA": hackrf.config.vga_gain
    }
    return {"status": "success", "message": "Global gain config updated. Active stream may not reflect change immediately.", "gains": current_gains}

@app.get("/api/gains")
async def get_gains():
    """Get current device gain values."""
    if not hackrf.device:
        # Fallback if device not initialized, return defaults or last known config
        logger.warning("get_gains called but HackRF device not fully initialized. Returning stored config.")
    current_gains = {
        "LNA": hackrf.config.lna_gain,
        "VGA": hackrf.config.vga_gain
    }
    return {"status": "success", "gains": current_gains}

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when shutting down."""
    logger.info("Shutting down server. Ensuring is_sweeping is false.")
    global is_sweeping #, sweep_task # sweep_task is disabled
    is_sweeping = False
    # if sweep_task:
    #     try: sweep_task.cancel(); await sweep_task
    #     except: pass 
    #     sweep_task = None
    if hackrf.device:
        try: await hackrf.cleanup() # Assuming hackrf.cleanup() is async or can be awaited
        except Exception as e: logger.error(f"Error during HackRF device cleanup on shutdown: {e}")
    logger.info("Cleanup attempt on shutdown complete.")

if __name__ == "__main__":
    import uvicorn
    # Ensure correct import path if running main.py directly for testing
    # This might require setting PYTHONPATH or using `python -m backend.main`
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False) # Disable reload for streamer stability 
