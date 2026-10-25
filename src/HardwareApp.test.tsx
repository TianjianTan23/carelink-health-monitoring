import React from 'react';
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {act,fireEvent,render,screen,cleanup,within} from '@testing-library/react';
import {HardwareApp} from './HardwareApp';
import {HardwareBridgeService,HardwareBridgeError} from './data/HardwareBridgeService';
import {hardwareConfig,hardwareFixture} from './test/hardwareFixture';
beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-23T06:44:14Z'));localStorage.setItem('carelink-v2-language','en');});
afterEach(()=>{cleanup();vi.useRealTimers();});
async function advance(ms:number){await act(async()=>{await vi.advanceTimersByTimeAsync(ms);});}
async function click(name:string){await act(async()=>{fireEvent.click(screen.queryByRole('button',{name})??screen.getByRole('tab',{name}));});}
async function start(){const service=new HardwareBridgeService(hardwareConfig);const latest=vi.spyOn(service,'latest').mockResolvedValue(hardwareFixture());render(<HardwareApp service={service}/>);await click('Open device workspace');return {latest};}
it('keeps the complete Pro dashboard, searchable device card, detail tabs, trends, history and AI unavailable area',async()=>{
 await start();expect(screen.getByRole('heading',{name:/Patients/})).toBeInTheDocument();expect(screen.getByLabelText('Search patients')).toBeInTheDocument();expect(screen.getAllByText('Heart rate').length).toBeGreaterThan(0);expect(screen.queryByText('SpO₂')).not.toBeInTheDocument();
 await click('Open esp32-01');expect(screen.getByRole('tab',{name:'Overview'})).toHaveAttribute('aria-selected','true');expect(screen.getByText('25.87')).toBeInTheDocument();expect(screen.getByText('0.92')).toBeInTheDocument();expect(screen.getAllByText(/Fall classification not yet validated/).length).toBeGreaterThan(0);
 expect(screen.getByRole('heading',{name:'Last 10 minutes: trends'})).toBeInTheDocument();await click('10-minute readings');expect(screen.getAllByRole('row')).toHaveLength(2);expect(screen.getByRole('columnheader',{name:'Bridge received'})).toBeInTheDocument();
 await click('Raw data & AI');expect(screen.getByRole('heading',{name:'AI predictions'})).toBeInTheDocument();expect(screen.getByText(/AI not connected/)).toBeInTheDocument();expect(screen.getByText('Not connected')).toBeInTheDocument();expect(screen.queryByText('SpO₂')).not.toBeInTheDocument();expect(screen.queryByText('Possible fall')).not.toBeInTheDocument();
});
it('Basic remains simplified without losing bilingual/theme controls or inventing health conclusions',async()=>{
 await start();await click('Try Basic mode');expect(screen.queryByRole('tab',{name:'Raw data & AI'})).not.toBeInTheDocument();expect(screen.getByText('25.87')).toBeInTheDocument();expect(screen.getAllByText('Heart rate').length).toBeGreaterThan(0);await click('Switch to dark');expect(document.documentElement.dataset.theme).toBe('dark');await click('中文');expect(screen.getByText('跌倒分类尚未验证')).toBeInTheDocument();
});
it('retains stale state across successful polls and recovers only on a new bridge receive time',async()=>{
 const {latest}=await start();await click('Try Basic mode');await advance(6000);expect(screen.queryByText('25.87')).not.toBeInTheDocument();expect(screen.getByText('Device offline or data stale')).toBeInTheDocument();latest.mockResolvedValue(hardwareFixture());await advance(1000);expect(screen.getByText('25.87')).toBeInTheDocument();
});
it('shows network failure and clears measurements when bridge restarts without hiding the product shell',async()=>{
 const {latest}=await start();latest.mockRejectedValue(new HardwareBridgeError('network','offline'));await advance(1000);expect(screen.getByRole('alert')).toHaveTextContent('Unable to load');expect(screen.getByLabelText('Search patients')).toBeInTheDocument();latest.mockRejectedValue(new HardwareBridgeError('waiting','waiting',503));await advance(1000);await click('Open esp32-01');expect(screen.getAllByText(/Waiting for/).length).toBeGreaterThan(0);expect(screen.queryByText('25.87')).not.toBeInTheDocument();
});
it('shows raw motion event timeline and records local review without declaring a fall',async()=>{
 await start();await click('Alerts');await act(async()=>{fireEvent.click(screen.getByRole('button',{name:/esp32-01.*Raw firmware alarm/}));});
 expect(screen.getByText('Event occurred')).toBeInTheDocument();await click('Acknowledge alert');expect(screen.getByRole('dialog')).toHaveTextContent('browser session only');await act(async()=>{fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Acknowledge'}));});expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(screen.queryByText('Possible fall')).not.toBeInTheDocument();
});

it('uses an honest hardware display concept without retired vitals or a validated-fall claim',async()=>{
 await start();await click('Device display');expect(screen.getByText(/Previews heart rate, surface temperature and acceleration/)).toBeInTheDocument();expect(screen.queryByText(/SpO₂|Fall events have priority/)).not.toBeInTheDocument();
});
