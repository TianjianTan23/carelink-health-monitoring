import type {HardwareConfig,HardwareSnapshot} from '../data/HardwareBridgeService';
// Test-only fixture based on field names observed on esp32-01. Never used at runtime.
export const hardwareConfig:HardwareConfig={mode:'hardware',baseUrl:'/hardware-bridge',pollIntervalMs:1000,staleAfterMs:5000,requestTimeoutMs:4000,deviceId:'esp32-01',heartRateContractConfirmed:false};
export function hardwareFixture(receivedAt=new Date().toISOString()):HardwareSnapshot{return {
  ok:true,received_at:receivedAt,data:{device_id:'esp32-01',uptime_ms:2301685,
    accel_x_g:-0.56,accel_y_g:-0.24,accel_z_g:0.68,accel_total_g:0.92,accel_peak_g:0.92,
    ambient_temp_c:25.89,object_temp_c:25.87,mpu6050_ok:true,mlx90614_ok:true,
    mpu6050_error:null,mlx90614_error:null,alarm:true,
    heart_rate_bpm:null,heart_rate_ok:false,heart_signal_raw:2262,
    heart_rate_error:'NO_STABLE_PULSE: place finger on sensor',heart_rate_alarm:false,
    buzzer_ok:true,buzzer_error:null,buzzer_on:false,lcd_ok:true,lcd_error:null,
    lcd_interface:'parallel_4bit',lcd_line_1:'HR: -- WAIT',lcd_line_2:'Body:25.8 C',
  },
};}
