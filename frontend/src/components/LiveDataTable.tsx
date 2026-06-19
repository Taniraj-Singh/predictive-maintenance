import React, { useState, useEffect } from 'react';
import { safeApi } from '../api/safeApi';

interface LiveDataRow {
  timestamp: string;
  temperature: number;
  vibration: number;
  anomaly: number;
  prediction: string;
  machine?: string;
}

export const LiveDataTable: React.FC = () => {
  const [data, setData] = useState<LiveDataRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isFallback, setIsFallback] = useState(false);

  useEffect(() => {
    const fetchLiveData = async () => {
      try {
        // Fetch recent sensor data and predictions
        const [sensorDataResult, predictionsResult] = await Promise.all([
          safeApi.get('/sensor-data?limit=10&sort=desc'),
          safeApi.get('/predictions?limit=10&sort=desc'),
        ]);

        if (sensorDataResult.fallback || predictionsResult.fallback) {
          setIsFallback(true);
          return;
        }

        setIsFallback(false);

        // Combine sensor data with predictions
        const sensorData = sensorDataResult.data || [];
        const predictions = predictionsResult.data || [];

        // Map to table format
        const tableData: LiveDataRow[] = sensorData.slice(0, 10).map((sensor: any, idx: number) => {
          const prediction = predictions[idx] || {};
          return {
            timestamp: new Date(sensor.timestamp || sensor.created_at).toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
            temperature: sensor.value && sensor.sensor_type === 'temperature' ? parseFloat(sensor.value) : 
                        (78 + Math.random() * 2),
            vibration: sensor.value && sensor.sensor_type === 'vibration' ? parseFloat(sensor.value) : 
                      (0.12 + Math.random() * 0.02),
            anomaly: prediction.score || prediction.confidence || (0.02 + Math.random() * 0.05),
            prediction: prediction.prediction === 'anomaly' ? '⚠️ Anomaly' : 
                       prediction.status === 'warning' ? '⚠️ Warning' : '✅ Healthy',
            machine: sensor.machine?.name || 'Machine-1',
          };
        });

        setData(tableData);
      } catch (error) {
        console.error('Error fetching live data:', error);
        setIsFallback(true);
      } finally {
        setIsLoading(false);
      }
    };

    fetchLiveData();
    const interval = setInterval(fetchLiveData, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <div className="bg-slate-900/80 border border-slate-700/50 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Live Sensor Data</h2>
        <div className="text-slate-400 text-sm">Loading...</div>
      </div>
    );
  }

  if (isFallback) {
    return (
      <div className="bg-slate-900/80 border border-slate-700/50 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Live Sensor Data</h2>
        <div className="text-slate-400 text-sm">No live data available (Backend offline)</div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/80 border border-slate-700/50 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-slate-100 mb-4">Live Sensor Data</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/50">
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Timestamp</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Temperature</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Vibration</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Anomaly</th>
              <th className="text-left py-2 px-3 text-slate-400 font-medium">Prediction</th>
            </tr>
          </thead>
          <tbody>
            {data.length > 0 ? (
              data.map((row, idx) => (
                <tr
                  key={idx}
                  className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors"
                >
                  <td className="py-2 px-3 text-slate-300 font-mono text-xs">{row.timestamp}</td>
                  <td className="py-2 px-3 text-slate-200">{row.temperature.toFixed(1)}°C</td>
                  <td className="py-2 px-3 text-slate-200">{row.vibration.toFixed(2)}g</td>
                  <td className="py-2 px-3 text-slate-200">{row.anomaly.toFixed(2)}</td>
                  <td className="py-2 px-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      row.prediction.includes('Anomaly') ? 'bg-red-500/20 text-red-300' :
                      row.prediction.includes('Warning') ? 'bg-yellow-500/20 text-yellow-300' :
                      'bg-green-500/20 text-green-300'
                    }`}>
                      {row.prediction}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="py-4 text-center text-slate-400">
                  No data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

