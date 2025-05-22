import React, { useMemo, useEffect, useRef } from 'react';
import { Paper, Typography, Box, Slider, FormControlLabel, Switch, Collapse } from '@mui/material';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// Reduce animation frame rate for less CPU usage
ChartJS.defaults.animation = {
  duration: 0 
};
ChartJS.defaults.datasets.line.pointRadius = 0;
ChartJS.defaults.elements.line.borderWidth = 1;

interface SpectrumData {
  frequencies: number[];
  magnitudes: number[];
  timestamp: number;
}

interface SpectrumDisplayProps {
  data: SpectrumData | null;
  error: string;
  overallMinFreqMHz?: number; // Optional for now, for smoother transition
  overallMaxFreqMHz?: number; // Optional for now
  filterMinDb?: number; // dB filter minimum
  filterMaxDb?: number; // dB filter maximum  
  filterEnabled?: boolean; // Enable/disable dB filtering
  onFilterMinDbChange?: (value: number) => void;
  onFilterMaxDbChange?: (value: number) => void;
  onFilterEnabledChange?: (enabled: boolean) => void;
  isRunning?: boolean; // Whether the scan is currently running
}

const SpectrumDisplay: React.FC<SpectrumDisplayProps> = ({ 
  data, 
  error, 
  overallMinFreqMHz, 
  overallMaxFreqMHz,
  filterMinDb = -100,
  filterMaxDb = 0,
  filterEnabled = false,
  onFilterMinDbChange,
  onFilterMaxDbChange,
  onFilterEnabledChange,
  isRunning = false
}) => {
  // Add a ref to the chart for direct access
  const chartRef = useRef<any>(null);
  
  // Display debug info
  useEffect(() => {
    if (data) {
      console.log(`Packet Frequency range: ${data.frequencies[0]/1e6}MHz to ${data.frequencies[data.frequencies.length-1]/1e6}MHz`);
    }
    if (overallMinFreqMHz && overallMaxFreqMHz) {
      console.log(`Overall Sweep range for X-axis: ${overallMinFreqMHz}MHz to ${overallMaxFreqMHz}MHz`);
    }
  }, [data, overallMinFreqMHz, overallMaxFreqMHz]);

  // Calculate dynamic min/max values for better visualization
  // Only do this calculation if we have data
  const { minPower, maxPower } = useMemo(() => {
    if (!data || !data.magnitudes.length) {
      return { minPower: -100, maxPower: -20 };
    }

    // Find a reasonable power range without scanning the whole array
    // Take samples from the array for faster calculation
    const step = Math.max(1, Math.floor(data.magnitudes.length / 20));
    const sampledValues = [];
    for (let i = 0; i < data.magnitudes.length; i += step) {
      sampledValues.push(data.magnitudes[i]);
    }
    
    const min = Math.max(-100, Math.min(...sampledValues) - 5);
    const max = Math.min(-20, Math.max(...sampledValues) + 5);

    return { minPower: min, maxPower: max };
  }, [data]);

  // Use the passed overall sweep frequencies for the X-axis if available, 
  // otherwise fallback to individual packet for compatibility or non-sweep scenarios.
  const displayFreqMin = overallMinFreqMHz !== undefined ? overallMinFreqMHz : (data ? data.frequencies[0] / 1e6 : 0);
  const displayFreqMax = overallMaxFreqMHz !== undefined ? overallMaxFreqMHz : (data ? data.frequencies[data.frequencies.length - 1] / 1e6 : 100);

  // Process data with optional dB filtering
  const { chartFreqs, chartMags, filteredIndices } = useMemo(() => {
    if (!data || !data.magnitudes.length) {
      return { chartFreqs: [], chartMags: [], filteredIndices: [] };
    }
    
    // Convert frequencies to MHz for display
    const freqs = data.frequencies.map(f => f / 1e6);
    let magnitudes = [...data.magnitudes];
    let indices: number[] = [];
    
    // Apply dB filtering if enabled
    if (filterEnabled) {
      indices = magnitudes
        .map((mag, idx) => ({ mag, idx }))
        .filter(({ mag }) => mag >= filterMinDb && mag <= filterMaxDb)
        .map(({ idx }) => idx);
    }
    
    return { 
      chartFreqs: freqs, 
      chartMags: magnitudes,
      filteredIndices: indices
    };
  }, [data, filterEnabled, filterMinDb, filterMaxDb]);

  // Force chart update when new data arrives
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.update();
    }
  }, [chartFreqs, chartMags]);

  const chartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    elements: {
      point: {
        radius: 0
      },
      line: {
        tension: 0.1
      }
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false
    },
    hover: {
      mode: 'nearest',
      intersect: false
    },
    scales: {
      x: {
        type: 'linear',
        display: true,
        position: 'bottom',
        bounds: 'data',
        min: overallMinFreqMHz !== undefined ? overallMinFreqMHz : (data?.frequencies[0] || 0) / 1e6,
        max: overallMaxFreqMHz !== undefined ? overallMaxFreqMHz : (data?.frequencies[data.frequencies.length - 1] || 100) / 1e6,
        title: {
          display: true,
          text: 'Frequency (MHz)'
        },
        ticks: {
          maxTicksLimit: 10,
          callback: function(tickValue: string | number) {
            return typeof tickValue === 'number' ? tickValue.toFixed(2) : tickValue;
          }
        }
      },
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        bounds: 'data',
        min: -100,
        max: 0,
        title: {
          display: true,
          text: 'Power (dB)'
        },
        grid: {
          color: 'rgba(255, 255, 255, 0.1)'
        },
        ticks: {
          // Optional: customize Y-axis ticks if needed
          // stepSize: 10 
        }
      }
    },
    plugins: {
      legend: {
        display: false
      },
      title: {
        display: true,
        text: 'HackRF Spectrum Analyzer'
      },
      tooltip: {
        enabled: true,
        mode: 'nearest',
        intersect: false,
        callbacks: {
          label: function(context) {
            return `Power: ${context.parsed.y.toFixed(1)} dB`;
          },
          title: function(context) {
            if (context[0] && context[0].parsed) {
              return `Frequency: ${context[0].parsed.x.toFixed(3)} MHz`;
            }
            return '';
          }
        }
      }
    }
  };

  const chartData = {
    labels: chartFreqs,
    datasets: filterEnabled && filteredIndices.length > 0 ? [
      // Main spectrum data (dimmed when filtering)
      {
        data: chartMags.map((y, i) => ({ x: chartFreqs[i], y })),
        borderColor: 'rgba(75, 192, 192, 0.3)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 1,
        pointRadius: 0,
        tension: 0,
        fill: false,
        spanGaps: true
      },
      // Highlighted filtered points
      {
        data: filteredIndices.map(i => ({ x: chartFreqs[i], y: chartMags[i] })),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.5)',
        borderWidth: 2,
        pointRadius: 1,
        tension: 0,
        fill: false,
        spanGaps: true
      }
    ] : [
      // Normal display when not filtering
      {
        data: chartMags.map((y, i) => ({ x: chartFreqs[i], y })),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0,
        fill: false,
        spanGaps: true
      }
    ]
  };

  if (error) {
    return (
      <Paper sx={{ p: 2, backgroundColor: 'error.dark' }}>
        <Typography color="error.contrastText">{error}</Typography>
      </Paper>
    );
  }

  // If no data yet, show loading message
  if (!data) {
    return (
      <Paper sx={{ p: 2, height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          Waiting for spectrum data...
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 2, height: '60vh' }}>
      {/* dB Filter Controls - only show when paused */}
      {!isRunning && data && onFilterEnabledChange && (
        <Box sx={{ mb: 2, p: 1, backgroundColor: 'rgba(255, 255, 255, 0.05)', borderRadius: 1 }}>
          <FormControlLabel
            control={
              <Switch 
                checked={filterEnabled} 
                onChange={(e) => onFilterEnabledChange(e.target.checked)}
                size="small"
              />
            }
            label="Enable dB Filter"
            sx={{ mb: 1 }}
          />
          <Collapse in={filterEnabled}>
            <Box sx={{ px: 2 }}>
              <Typography variant="body2" gutterBottom>
                Filter Range: {filterMinDb}dB to {filterMaxDb}dB 
                {filteredIndices.length > 0 && ` (${filteredIndices.length} points highlighted)`}
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption">Min dB:</Typography>
                  <Slider
                    value={filterMinDb}
                    onChange={(_, value) => onFilterMinDbChange && onFilterMinDbChange(value as number)}
                    min={-100}
                    max={0}
                    step={1}
                    size="small"
                    valueLabelDisplay="auto"
                  />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption">Max dB:</Typography>
                  <Slider
                    value={filterMaxDb}
                    onChange={(_, value) => onFilterMaxDbChange && onFilterMaxDbChange(value as number)}
                    min={-100}
                    max={0}
                    step={1}
                    size="small"
                    valueLabelDisplay="auto"
                  />
                </Box>
              </Box>
            </Box>
          </Collapse>
        </Box>
      )}
      
      <Box sx={{ width: '100%', height: '100%', position: 'relative' }}>
        <Line 
          ref={chartRef}
          options={chartOptions} 
          data={chartData} 
        />
        <Box sx={{ position: 'absolute', bottom: 5, right: 10, fontSize: '0.75rem', color: 'text.secondary' }}>
          {data ? data.magnitudes.length : 0} points | {displayFreqMin.toFixed(2)} - {displayFreqMax.toFixed(2)} MHz
          {filterEnabled && filteredIndices.length > 0 && (
            <Box component="span" sx={{ color: 'rgb(255, 99, 132)', ml: 1 }}>
              | {filteredIndices.length} filtered
            </Box>
          )}
        </Box>
      </Box>
    </Paper>
  );
};

// Use React.memo to prevent unnecessary re-renders
export default React.memo(SpectrumDisplay); 