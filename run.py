#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import signal
import logging
from typing import List, Optional
import socket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServerManager:
    def __init__(self):
        self.frontend_process: Optional[subprocess.Popen] = None
        self.backend_process: Optional[subprocess.Popen] = None
        self.running = True

    def start_backend(self):
        """Start the FastAPI backend server."""
        try:
            # First check if port 8000 is already in use
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 8000))
            sock.close()
            
            if result == 0:
                logger.error("Port 8000 is already in use. Another instance of the server might be running.")
                logger.info("Attempting to terminate any existing processes using port 8000...")
                # Try to terminate existing process (Linux/macOS only)
                try:
                    subprocess.run("lsof -ti tcp:8000 | xargs kill -9", shell=True, check=True)
                    time.sleep(1)  # Give time for process to terminate
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to terminate existing process using lsof: {e}")
                    logger.error("Please manually terminate any process using port 8000 and try again.")
                    sys.exit(1)
                except FileNotFoundError:
                    logger.warning("lsof command not found. Skipping process termination. This might be an issue if a process is already using port 8000.")
                except Exception as e:
                    logger.error(f"An unexpected error occurred while trying to terminate existing process: {e}")
                    logger.error("Please manually terminate any process using port 8000 and try again.")
                    sys.exit(1)
            
            # Start the backend with enhanced error reporting
            self.backend_process = subprocess.Popen(
                ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Check if process started successfully
            time.sleep(1)
            if self.backend_process.poll() is not None:
                # Process exited immediately
                stdout, stderr = self.backend_process.communicate()
                logger.error(f"Backend server failed to start:\n{stderr}")
                sys.exit(1)
                
            logger.info("Backend server started")
        except Exception as e:
            logger.error(f"Failed to start backend server: {e}")
            sys.exit(1)

    def start_frontend(self):
        """Start the React development server."""
        try:
            os.chdir("frontend")
            self.frontend_process = subprocess.Popen(
                ["npm", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            os.chdir("..")
            logger.info("Frontend development server started")
        except Exception as e:
            logger.error(f"Failed to start frontend server: {e}")
            sys.exit(1)

    def stop_servers(self):
        """Stop both servers gracefully."""
        if self.frontend_process:
            logger.info("Stopping frontend server...")
            self.frontend_process.terminate()
            try:
                self.frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Frontend server did not terminate in time, forcing...")
                self.frontend_process.kill()

        if self.backend_process:
            logger.info("Stopping backend server...")
            self.backend_process.terminate()
            try:
                self.backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Backend server did not terminate in time, forcing...")
                self.backend_process.kill()
            
            # Make sure to also terminate any lingering HackRF processes
            try:
                subprocess.run(["pkill", "-f", "hackrf"], check=False)
            except FileNotFoundError:
                logger.warning("pkill command not found. Skipping HackRF process termination.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Error attempting to kill HackRF processes: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while trying to kill HackRF processes: {e}")

    def handle_signal(self, signum, frame):
        """Handle interrupt signals."""
        logger.info("Received interrupt signal. Shutting down servers...")
        self.running = False
        self.stop_servers()
        sys.exit(0)

    def monitor_processes(self):
        """Monitor server processes and their output."""
        while self.running:
            if self.backend_process:
                output = self.backend_process.stdout.readline()
                if output:
                    print("[Backend]", output.strip())

            if self.frontend_process:
                output = self.frontend_process.stdout.readline()
                if output:
                    print("[Frontend]", output.strip())

            # Check if either process has terminated
            if (self.backend_process and self.backend_process.poll() is not None) or \
               (self.frontend_process and self.frontend_process.poll() is not None):
                logger.error("One of the servers has terminated unexpectedly")
                self.running = False
                self.stop_servers()
                sys.exit(1)

            time.sleep(0.1)

def main():
    manager = ServerManager()

    # Set up signal handlers
    signal.signal(signal.SIGINT, manager.handle_signal)
    signal.signal(signal.SIGTERM, manager.handle_signal)

    try:
        # Start servers
        manager.start_backend()
        manager.start_frontend()

        # Monitor processes
        manager.monitor_processes()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        manager.stop_servers()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        manager.stop_servers()
        sys.exit(1)

if __name__ == "__main__":
    main() 
