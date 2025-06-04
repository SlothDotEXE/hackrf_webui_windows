import numpy as np
from scipy import signal
from typing import Tuple, List
import logging

logger = logging.getLogger(__name__)

class SignalProcessor:
    def __init__(self, sample_rate: float = 2e6):
        self.sample_rate = sample_rate
        self.deemph = self._create_deemphasis_filter()
        
    def _create_deemphasis_filter(self, tau: float = 75e-6) -> Tuple[np.ndarray, np.ndarray]:
        """Create de-emphasis filter coefficients (75µs time constant for FM broadcast)."""
        omega = 1 / tau
        b = [1]
        a = [1 / omega, 1]
        return signal.bilinear(b, a, fs=self.sample_rate)

    def process_spectrum(self, samples: np.ndarray, window: str = 'hann') -> np.ndarray:
        """Convert time domain samples to frequency domain power spectrum."""
        if len(samples) == 0:
            return np.array([])
            
        # Apply window function
        windowed = samples * signal.get_window(window, len(samples))
        
        # Compute FFT and shift
        spectrum = np.fft.fftshift(np.fft.fft(windowed))
        
        # Convert to power in dB
        power_db = 20 * np.log10(np.abs(spectrum) + 1e-10)
        
        return power_db
        
    def demodulate_fm(self, samples: np.ndarray) -> np.ndarray:
        """Demodulate FM signal to audio."""
        if len(samples) == 0:
            return np.array([])
            
        # FM demodulation through phase difference
        diff = np.angle(samples[1:] * np.conj(samples[:-1]))
        
        # Apply de-emphasis filter
        audio = signal.lfilter(*self.deemph, diff)
        
        # Normalize
        audio = audio / np.max(np.abs(audio))
        
        return audio
        
    def resample_audio(self, audio: np.ndarray, target_rate: float = 48000) -> np.ndarray:
        """Resample audio to target sample rate."""
        if len(audio) == 0:
            return np.array([])
            
        # Calculate resampling ratio
        ratio = target_rate / self.sample_rate
        
        # Resample using polyphase filtering
        resampled = signal.resample_poly(audio, up=int(target_rate), down=int(self.sample_rate))
        
        return resampled
        
    def process_chunk(self, samples: np.ndarray, mode: str = 'spectrum') -> np.ndarray:
        """Process a chunk of samples in either spectrum or FM demod mode."""
        try:
            if mode == 'spectrum':
                return self.process_spectrum(samples)
            elif mode == 'fm':
                demodulated = self.demodulate_fm(samples)
                return self.resample_audio(demodulated)
            else:
                raise ValueError(f"Unknown processing mode: {mode}")
                
        except Exception as e:
            logger.error(f"Error processing chunk in {mode} mode: {e}")
            return np.array([])
            
    def apply_gain(self, samples: np.ndarray, gain_db: float) -> np.ndarray:
        """Apply gain to samples in dB."""
        return samples * (10 ** (gain_db / 20))
        
    def filter_bandwidth(self, samples: np.ndarray, bandwidth: float) -> np.ndarray:
        """Apply bandwidth filter to samples."""
        if bandwidth >= self.sample_rate:
            return samples
            
        nyq = self.sample_rate / 2
        b, a = signal.butter(5, bandwidth/nyq)
        return signal.filtfilt(b, a, samples) 
