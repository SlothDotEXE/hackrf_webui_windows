import React from 'react';
import {
  Paper,
  Button,
  Slider,
  Typography,
  Box,
  Stack,
  TextField,
  ButtonGroup
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';

interface ControlPanelProps {
  isRunning: boolean;
  startFreq: number;
  stopFreq: number;
  lnaGain: number;
  vgaGain: number;
  onStartStop: () => void;
  onStartFreqChange: (value: number) => void;
  onStopFreqChange: (value: number) => void;
  onLnaGainChange: (value: number) => void;
  onVgaGainChange: (value: number) => void;
}

const PRESETS = {
  'FM Radio': { start: 88e6, stop: 108e6 },
  'Aircraft Band': { start: 118e6, stop: 137e6 },
  'Weather Radio': { start: 162.4e6, stop: 162.55e6 }
};

const ControlPanel: React.FC<ControlPanelProps> = ({
  isRunning,
  startFreq,
  stopFreq,
  lnaGain,
  vgaGain,
  onStartStop,
  onStartFreqChange,
  onStopFreqChange,
  onLnaGainChange,
  onVgaGainChange
}) => {
  const formatFrequency = (value: number) => `${(value / 1e6).toFixed(3)} MHz`;
  const formatGain = (value: number) => `${value} dB`;

  const handleStartFreqChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(event.target.value) * 1e6; // Convert MHz to Hz
    if (!isNaN(value)) {
      onStartFreqChange(value);
    }
  };

  const handleStopFreqChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(event.target.value) * 1e6; // Convert MHz to Hz
    if (!isNaN(value)) {
      onStopFreqChange(value);
    }
  };

  const handlePresetClick = (preset: keyof typeof PRESETS) => {
    onStartFreqChange(PRESETS[preset].start);
    onStopFreqChange(PRESETS[preset].stop);
  };

  return (
    <Paper sx={{ p: 2, mt: 2 }}>
      <Stack spacing={3}>
        {/* Control Row */}
        <Stack direction="row" spacing={3}>
          {/* Start/Stop Button */}
          <Box sx={{ width: '20%' }}>
            <Button
              variant="contained"
              color={isRunning ? "error" : "success"}
              onClick={onStartStop}
              startIcon={isRunning ? <StopIcon /> : <PlayArrowIcon />}
              fullWidth
            >
              {isRunning ? "Stop" : "Start"}
            </Button>
          </Box>

          {/* Frequency Range Inputs */}
          <Box sx={{ width: '40%' }}>
            <Typography gutterBottom>Frequency Range (MHz)</Typography>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Start"
                type="number"
                value={(startFreq / 1e6).toFixed(3)}
                onChange={handleStartFreqChange}
                size="small"
                inputProps={{ step: 0.001 }}
              />
              <TextField
                label="Stop"
                type="number"
                value={(stopFreq / 1e6).toFixed(3)}
                onChange={handleStopFreqChange}
                size="small"
                inputProps={{ step: 0.001 }}
              />
            </Stack>
          </Box>

          {/* Presets */}
          <Box sx={{ width: '40%' }}>
            <Typography gutterBottom>Presets</Typography>
            <ButtonGroup variant="outlined" size="small">
              {Object.keys(PRESETS).map((preset) => (
                <Button
                  key={preset}
                  onClick={() => handlePresetClick(preset as keyof typeof PRESETS)}
                >
                  {preset}
                </Button>
              ))}
            </ButtonGroup>
          </Box>
        </Stack>

        {/* Gain Controls */}
        <Stack direction="row" spacing={3}>
          {/* LNA Gain */}
          <Box sx={{ width: '50%' }}>
            <Typography gutterBottom>LNA Gain</Typography>
            <Slider
              value={lnaGain}
              min={0}
              max={40}
              step={8}
              onChange={(_, value) => onLnaGainChange(value as number)}
              valueLabelDisplay="auto"
              valueLabelFormat={formatGain}
              marks
            />
            <Typography variant="body2" color="text.secondary" align="center">
              {formatGain(lnaGain)}
            </Typography>
          </Box>

          {/* VGA Gain */}
          <Box sx={{ width: '50%' }}>
            <Typography gutterBottom>VGA Gain</Typography>
            <Slider
              value={vgaGain}
              min={0}
              max={62}
              step={2}
              onChange={(_, value) => onVgaGainChange(value as number)}
              valueLabelDisplay="auto"
              valueLabelFormat={formatGain}
              marks
            />
            <Typography variant="body2" color="text.secondary" align="center">
              {formatGain(vgaGain)}
            </Typography>
          </Box>
        </Stack>
      </Stack>
    </Paper>
  );
};

export default ControlPanel; 
