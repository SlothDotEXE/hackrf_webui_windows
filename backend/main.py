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
from dsp import SignalProcessor
import time
from device import HackRFDevice, DeviceConfig
from starlette.websockets import WebSocketDisconnect

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
    "start_freq": 0,
    "stop_freq": 0,
    "step_size": 20e6,  # 20MHz steps (HackRF's instantaneous bandwidth)
    "current_freq": 0,
    "sample_rate": 20e6,
    "last_update": None
}

# Add SignalProcessor instance to global state
signal_processor = SignalProcessor(sample_rate=20e6)

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
            # Convert SoapySDRKwargs to dict
            result_dict = {key: result[key] for key in result.keys()}
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

def configure_device_for_frequency(freq: float, bandwidth: float = 20e6):
    """Configure device for a specific frequency."""
    if not hackrf.device:
        return False
    
    try:
        # Update device configuration 
        hackrf.config.center_freq = freq
        hackrf.config.sample_rate = min(current_sweep_config["sample_rate"], bandwidth)
        hackrf.config.bandwidth = bandwidth
        
        # Apply the configuration
        print(f"Setting sample rate to {hackrf.config.sample_rate/1e6:.2f}MHz")
        print(f"Setting center frequency to {freq/1e6:.2f}MHz")
        print(f"Setting bandwidth to {bandwidth/1e6:.2f}MHz")
        print("Setting gains: LNA=32, VGA=20")
        
        hackrf.apply_config()
        
        # Allow device to settle
        time.sleep(0.01)
        
        # Clear any stale data in device buffers
        hackrf.set_frequency(freq + 1)  # Small offset
        time.sleep(0.001)
        hackrf.set_frequency(freq)  # Back to desired frequency
        
        print("Device configuration complete")
        return True
    except Exception as e:
        print(f"Error configuring device for frequency {freq/1e6:.2f}MHz: {e}")
        return False

async def sweep_frequency():
    """Sweep through frequencies in steps."""
    global current_sweep_config, is_sweeping
    
    print("Starting frequency sweep")  # Mandatory print
    
    try:
        while is_sweeping:
            current_freq = current_sweep_config["current_freq"]
            
            if current_freq > current_sweep_config["stop_freq"]:
                # Reset to start frequency
                print("Resetting to start frequency")  # Mandatory print
                current_sweep_config["current_freq"] = current_sweep_config["start_freq"]
                continue
            
            # Configure device for current frequency
            print(f"Sweeping to {current_freq/1e6:.2f}MHz")  # Mandatory print
            if configure_device_for_frequency(current_freq):
                # Move to next frequency step
                current_sweep_config["current_freq"] += current_sweep_config["step_size"]
                # Small delay to allow device to settle
                await asyncio.sleep(0.05)
            else:
                print(f"Failed to configure frequency {current_freq/1e6:.2f}MHz")  # Mandatory print
                await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"Error in sweep: {e}")  # Mandatory print
        is_sweeping = False
    finally:
        print("Sweep task ended")  # Mandatory print

@app.post("/api/sweep/start")
async def start_sweep(
    start_freq: float = Body(...),
    stop_freq: float = Body(...),
    sample_rate: float = Body(default=20e6)
):
    """Start spectrum sweep."""
    global sweep_task, is_sweeping, current_sweep_config
    
    print(f"Starting sweep from {start_freq/1e6:.2f}MHz to {stop_freq/1e6:.2f}MHz")  # Mandatory print
    
    if is_sweeping:
        raise HTTPException(status_code=400, detail="Sweep already in progress")
    
    try:
        # Validate frequency range
        if start_freq >= stop_freq:
            raise HTTPException(status_code=400, detail="Start frequency must be less than stop frequency")
        
        if not hackrf.device:
            devices = get_hackrf_devices()
            print(f"Found devices: {devices}")  # Mandatory print
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            try:
                print("Initializing HackRF device...")  # Mandatory print
                success = await hackrf.initialize()
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to initialize HackRF device")
                print("HackRF device initialized successfully")  # Mandatory print
            except Exception as e:
                print(f"Failed to initialize device: {str(e)}")  # Mandatory print
                raise HTTPException(status_code=500, detail=f"Failed to initialize device: {str(e)}")
        
        # Configure sweep parameters
        current_sweep_config.update({
            "start_freq": start_freq,
            "stop_freq": stop_freq,
            "current_freq": start_freq,
            "sample_rate": sample_rate,
            "step_size": 20e6,  # 20MHz steps
            "last_update": None
        })
        
        print("Configuring initial frequency...")  # Mandatory print
        if not configure_device_for_frequency(start_freq):
            raise HTTPException(status_code=500, detail="Failed to configure initial frequency")
        
        is_sweeping = True
        print("Starting sweep task...")  # Mandatory print
        sweep_task = asyncio.create_task(sweep_frequency())
        print("Sweep task created")  # Mandatory print
        
        return {"status": "success", "message": "Sweep started"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error starting sweep: {str(e)}")  # Mandatory print
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/sweep/stop")
async def stop_sweep():
    """Stop spectrum sweep."""
    global sweep_task, is_sweeping
    
    if not is_sweeping:
        raise HTTPException(status_code=400, detail="No sweep in progress")
    
    try:
        is_sweeping = False
        if sweep_task:
            await sweep_task
            sweep_task = None
            
        return {"status": "success", "message": "Sweep stopped"}
        
    except Exception as e:
        logger.error(f"Error stopping sweep: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/spectrum")
async def websocket_spectrum(websocket: WebSocket):
    """WebSocket endpoint for streaming spectrum data."""
    global is_sweeping, current_sweep_config
    
    print("New WebSocket connection attempt")
    await websocket.accept()
    print("WebSocket connection accepted")
    
    # Use a simple buffer for spectrum data
    buffer_size = 8192
    buffer = np.zeros(buffer_size, np.complex64)
    
    # Track if we've sent data for this frequency
    last_freq = 0
    data_sent = False
    rx_stream = None
    
    try:
        if not hackrf.device:
            print("No active device available")
            await websocket.send_json({
                "type": "error",
                "message": "No HackRF device available. Please check connections and refresh."
            })
            await websocket.close()
            return
            
        # Create separate polling task that's easier to cancel
        async def poll_spectrum_data():
            nonlocal data_sent, last_freq, rx_stream
            
            try:
                # Skip this cycle if we're not sweeping
                if not is_sweeping:
                    return
                    
                # Skip if frequency hasn't changed and we already sent data
                current_freq = current_sweep_config["current_freq"]
                if current_freq == last_freq and data_sent:
                    return
                    
                last_freq = current_freq
                data_sent = False
                
                # Make sure any previous stream is fully closed before creating a new one
                if rx_stream is not None:
                    try:
                        hackrf.device.deactivateStream(rx_stream)
                        hackrf.device.closeStream(rx_stream)
                        rx_stream = None
                        # Small delay to ensure stream is fully released
                        await asyncio.sleep(0.1)  # Increased delay to ensure proper cleanup
                    except Exception as e:
                        print(f"Error closing previous stream: {e}")
                        await asyncio.sleep(0.5)  # Longer delay after error
                
                # Check for any potential resource conflicts
                try:
                    # Try to setup stream
                    rx_stream = hackrf.device.setupStream(SoapySDR.SOAPY_SDR_RX, "CF32", [0])
                    
                    # Try to activate stream with error handling
                    try:
                        hackrf.device.activateStream(rx_stream)
                    except Exception as activate_error:
                        error_message = str(activate_error)
                        print(f"[ERROR] Activate RX Stream Failed: {error_message}")
                        
                        if "Resource busy" in error_message:
                            # Send specific error message to frontend
                            await websocket.send_json({
                                "type": "error",
                                "message": "HackRF device is busy. Please close any other applications using it and try again."
                            })
                            
                            # Clean up and wait
                            if rx_stream is not None:
                                try:
                                    hackrf.device.closeStream(rx_stream)
                                    rx_stream = None
                                except:
                                    pass
                            
                            # Return early without crashing
                            return
                        else:
                            # Re-raise other errors
                            raise activate_error
                    
                    # Read samples (one-shot)
                    status = hackrf.device.readStream(rx_stream, [buffer], len(buffer), timeoutUs=100000)
                    
                    if status.ret > 0:
                        # Process samples
                        samples = buffer[:status.ret]
                        
                        # Apply window and compute FFT
                        windowed = samples * signal.windows.blackman(len(samples))
                        spectrum = np.fft.fftshift(np.fft.fft(windowed))
                        
                        # Convert to power in dB
                        power_db = 20 * np.log10(np.abs(spectrum) + 1e-10)
                        power_db = np.clip(power_db, -100, 0)
                        
                        # Reduce data size with decimation
                        decimation = 4
                        power_db = power_db[::decimation]
                        
                        # Calculate frequency points
                        center_freq = current_sweep_config["current_freq"]
                        sample_rate = current_sweep_config["sample_rate"]
                        start_freq = center_freq - (sample_rate / 2)
                        end_freq = center_freq + (sample_rate / 2)
                        
                        # Generate frequencies
                        num_points = len(power_db)
                        freqs = np.linspace(start_freq, end_freq, num_points).tolist()
                        magnitudes = power_db.tolist()
                        
                        # Validate data before sending
                        if len(freqs) != len(magnitudes) or len(freqs) == 0:
                            print(f"Warning: Invalid data sizes - freqs: {len(freqs)}, magnitudes: {len(magnitudes)}")
                        else:
                            min_power = min(magnitudes)
                            max_power = max(magnitudes)
                            min_freq = freqs[0] / 1e6
                            max_freq = freqs[-1] / 1e6
                            
                            print(f"Data range: {min_freq:.2f}-{max_freq:.2f} MHz, Power: {min_power:.1f} to {max_power:.1f} dB")
                            
                            # Send data
                            await websocket.send_json({
                                "type": "spectrum",
                                "frequencies": freqs,
                                "magnitudes": magnitudes,
                                "timestamp": int(time.time() * 1000)
                            })
                            
                            print(f"Sent data: {num_points} points at {center_freq/1e6:.2f} MHz")
                            data_sent = True
                
                finally:
                    # Always clean up stream immediately after use
                    if rx_stream is not None:
                        try:
                            hackrf.device.deactivateStream(rx_stream)
                            hackrf.device.closeStream(rx_stream)
                            rx_stream = None
                        except Exception as e:
                            print(f"Error closing stream: {e}")
            
            except Exception as e:
                print(f"Error in polling task: {e}")
                # Send error to frontend
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error processing spectrum data: {str(e)}"
                    })
                except:
                    pass
                
        # Main WebSocket loop
        while True:
            # Check if connection is still alive
            try:
                # Ping to check connection
                await websocket.send_text("ping")
                pong = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                
                if not is_sweeping:
                    await asyncio.sleep(0.2)
                    continue
                    
                # Do the spectrum polling in a way that's safe to cancel
                try:
                    await poll_spectrum_data()
                    # Add delay to prevent too many requests
                    await asyncio.sleep(0.5)  # Increased delay to reduce resource contention
                except asyncio.CancelledError:
                    print("Polling task cancelled")
                    break
                except Exception as e:
                    print(f"Error in main loop: {e}")
                    # Send error to frontend
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"WebSocket error: {str(e)}"
                        })
                    except:
                        pass
                    await asyncio.sleep(0.5)  # Increased delay after errors
            except (asyncio.TimeoutError, WebSocketDisconnect) as e:
                print(f"WebSocket connection lost: {str(e)}")
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
                
    except Exception as e:
        print(f"WebSocket error: {e}")
        # Try to send error to client
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"WebSocket connection error: {str(e)}"
            })
        except:
            pass
    finally:
        # Ensure we clean up the stream if it exists
        if 'rx_stream' in locals() and rx_stream is not None:
            try:
                hackrf.device.deactivateStream(rx_stream)
                hackrf.device.closeStream(rx_stream)
            except Exception as e:
                print(f"Error during final stream cleanup: {e}")
        
        try:
            await websocket.close()
        except:
            pass
        print("WebSocket connection closed")

@app.post("/api/tune")
async def tune_frequency(freq: float, sample_rate: float = 2e6):
    """Tune to a specific frequency for FM demodulation."""
    global is_sweeping
    
    if is_sweeping:
        await stop_sweep()
    
    try:
        if not hackrf.device:
            devices = get_hackrf_devices()
            if not devices:
                raise HTTPException(status_code=404, detail="No HackRF devices found")
            
            success = await hackrf.initialize()
            if not success:
                raise HTTPException(status_code=500, detail="Failed to initialize HackRF device")
        
        # Configure device for FM reception
        hackrf.config.sample_rate = sample_rate
        hackrf.config.center_freq = freq
        hackrf.apply_config()
        
        return {"status": "success", "message": f"Tuned to {freq/1e6:.2f} MHz"}
        
    except Exception as e:
        logger.error(f"Error tuning frequency: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gains")
async def set_gains(gains: Dict[str, int] = Body(...)):
    """Set device gain values."""
    try:
        if not hackrf.device:
            raise HTTPException(status_code=400, detail="No active device")
            
        logger.info(f"Setting gains: {gains}")
        
        # Update gains
        if "LNA" in gains:
            hackrf.config.lna_gain = gains["LNA"]
        if "VGA" in gains:
            hackrf.config.vga_gain = gains["VGA"]
            
        # Apply the updated gains
        hackrf.set_gains(hackrf.config.lna_gain, hackrf.config.vga_gain)
        
        # Return current gain values
        current_gains = {
            "LNA": hackrf.config.lna_gain,
            "VGA": hackrf.config.vga_gain
        }
        
        return {"status": "success", "gains": current_gains}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error setting gains: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/api/gains")
async def get_gains():
    """Get current device gain values."""
    try:
        if not hackrf.device:
            raise HTTPException(status_code=400, detail="No active device")
            
        # Get current gain values
        current_gains = {
            "LNA": hackrf.config.lna_gain,
            "VGA": hackrf.config.vga_gain
        }
        
        return {"status": "success", "gains": current_gains}
        
    except Exception as e:
        logger.error(f"Error getting gains: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when shutting down."""
    print("Shutting down server")
    global is_sweeping, sweep_task
    
    # Stop any active sweep
    is_sweeping = False
    
    # Wait for sweep task to complete if it exists
    if sweep_task:
        try:
            await sweep_task
        except asyncio.CancelledError:
            print("Sweep task cancelled during shutdown")
        except Exception as e:
            print(f"Error during sweep task shutdown: {e}")
        sweep_task = None
    
    # Clean up device resources
    try:
        await hackrf.cleanup()
    except Exception as e:
        print(f"Error during device cleanup: {e}")
    
    print("Cleanup complete")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 