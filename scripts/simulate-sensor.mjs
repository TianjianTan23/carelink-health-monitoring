const options = Object.fromEntries(
  process.argv.slice(2).map(argument => {
    const [key, ...rest] = argument.replace(/^--/, '').split('=');
    return [key, rest.join('=')];
  }),
);

const url = options.url || 'http://127.0.0.1:8000/sensor-data';
const intervalMs = Number(options.interval || 1000);
const fixedScenario = options.scenario || 'cycle';

if (!Number.isFinite(intervalMs) || intervalMs < 250) {
  throw new Error('--interval must be at least 250 milliseconds');
}
if (!['cycle', 'normal', 'warning', 'critical'].includes(fixedScenario)) {
  throw new Error('--scenario must be cycle, normal, warning, or critical');
}

let sample = 0;
let stopped = false;
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const scenarioFor = index => {
  if (fixedScenario !== 'cycle') return fixedScenario;
  const phase = index % 35;
  if (phase < 20) return 'normal';
  if (phase < 30) return 'warning';
  return 'critical';
};

const readingFor = index => {
  const scenario = scenarioFor(index);
  const wave = Math.sin(index / 2.4);
  if (scenario === 'warning') {
    return {scenario, heart_rate_bpm: 111 + wave * 3, object_temp_c: 36.8 + wave * 0.1, fall_detected: false};
  }
  if (scenario === 'critical') {
    return {scenario, heart_rate_bpm: 139 + wave * 4, object_temp_c: 39.4 + wave * 0.15, fall_detected: index % 5 === 0};
  }
  return {scenario, heart_rate_bpm: 74 + wave * 5, object_temp_c: 36.6 + wave * 0.15, fall_detected: false};
};

process.on('SIGINT', () => { stopped = true; });
process.on('SIGTERM', () => { stopped = true; });

console.log(`Sending synthetic coursework readings to ${url}`);
console.log('Press Ctrl+C to stop. This exercises the real FastAPI, model, SQLite, alerts, and live UI.');

while (!stopped) {
  const reading = readingFor(sample++);
  const payload = {
    device_id: 'carelink-simulator',
    heart_rate_bpm: Number(reading.heart_rate_bpm.toFixed(1)),
    object_temp_c: Number(reading.object_temp_c.toFixed(2)),
    fall_detected: reading.fall_detected,
    accel_x_g: 0.02,
    accel_y_g: 0.03,
    accel_z_g: reading.fall_detected ? 2.8 : 1.0,
  };
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${JSON.stringify(result)}`);
    console.log(`${new Date().toLocaleTimeString()} ${reading.scenario.padEnd(8)} HR=${payload.heart_rate_bpm} TEMP=${payload.object_temp_c} FALL=${payload.fall_detected} -> ${result.label ?? 'unavailable'}`);
  } catch (error) {
    console.error(`Cannot reach CareLink API: ${error instanceof Error ? error.message : String(error)}`);
    console.error('Run npm start in another Terminal window and keep it open.');
  }
  await pause(intervalMs);
}

console.log('Sensor simulator stopped.');
