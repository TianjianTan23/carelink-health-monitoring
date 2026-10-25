import React from 'react';
import {it,expect,vi} from 'vitest';
import {render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {App} from './App';
import {MockDataService} from './data/MockDataService';
import {LiveApiService} from './data/LiveApiService';
import {defaultConfig} from './data/config';
import sessions from '../shared/demo-sessions.json';
async function startBasic(){const user=userEvent.setup();const service=new MockDataService();render(<App service={service}/>);await user.click(screen.getByRole('button',{name:/English/}));await user.click(screen.getByRole('button',{name:/Basic/}));await user.click(screen.getByRole('button',{name:/Sign in to demo/}));await screen.findByRole('heading',{name:'Xu Wangshu'});return {user,service};}
it('Basic shows linked patient only, changes language/theme, and shows unavailable/error states',async()=>{
 const {user}=await startBasic();expect(screen.queryByText('Lin Zhiqiu')).not.toBeInTheDocument();expect(screen.queryByText('Raw sensor data')).not.toBeInTheDocument();
 await user.click(screen.getByRole('button',{name:'Switch to dark'}));expect(document.documentElement.dataset.theme).toBe('dark');
 await user.click(screen.getByRole('button',{name:'Demo scenarios'}));const dialog=screen.getByRole('dialog');await user.click(within(dialog).getByRole('button',{name:'Heart rate unavailable'}));await user.click(within(dialog).getByRole('button',{name:'Close'}));await screen.findAllByText('Waiting for a valid heart-rate signal');expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
 await user.click(screen.getByRole('button',{name:'Demo scenarios'}));await user.click(screen.getByLabelText('Simulate network failure'));await user.click(screen.getByRole('button',{name:'Close'}));await screen.findByRole('alert');expect(screen.getByText('Unable to load')).toBeInTheDocument();
 await user.click(screen.getByRole('button',{name:'中文'}));expect(screen.getByText('加载失败')).toBeInTheDocument();
});
it('Pro searches patients, opens correct details, reads history/raw/AI and acknowledges alert',async()=>{
 const user=userEvent.setup();render(<App service={new MockDataService()}/>);await user.click(screen.getByRole('button',{name:'English'}));await user.click(screen.getByRole('button',{name:'Sign in to demo'}));await screen.findByRole('heading',{name:/Patients/});
 await user.type(screen.getByLabelText('Search patients'),'Lin');await user.click(screen.getByRole('button',{name:'Open Lin Zhiqiu'}));await screen.findByRole('heading',{name:'Lin Zhiqiu'});expect(screen.getByRole('tab',{name:'Overview'})).toHaveAttribute('aria-selected','true');await user.click(screen.getByRole('tab',{name:'10-minute readings'}));await screen.findByRole('heading',{name:'Last 10 minutes: readings'});expect(screen.getAllByRole('row').length).toBeGreaterThan(10);await user.click(screen.getByRole('tab',{name:'Raw data & AI'}));expect(screen.getByRole('heading',{name:'AI predictions'})).toBeInTheDocument();expect(screen.getByRole('heading',{name:'Raw sensor data'})).toBeInTheDocument();
 await user.click(screen.getByRole('button',{name:'View alert history'}));await screen.findByRole('heading',{name:'Alerts'});const records=await screen.findAllByRole('button',{name:/p001.*Review urgently/});await user.click(records[0]);await user.click(screen.getByRole('button',{name:'Acknowledge alert'}));await user.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Acknowledge'}));await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());expect(screen.getAllByText('Acknowledged').length).toBeGreaterThan(0);
});
it('login validates blank credentials and simulated rejection without authenticating real users',async()=>{
 const user=userEvent.setup();render(<App service={new MockDataService()}/>);await user.click(screen.getByRole('button',{name:'English'}));await user.clear(screen.getByLabelText('Email or username'));await user.click(screen.getByRole('button',{name:'Sign in to demo'}));expect(screen.getByRole('alert')).toHaveTextContent('Enter an email');await user.type(screen.getByLabelText('Email or username'),'demo');await user.clear(screen.getByLabelText('Password'));await user.type(screen.getByLabelText('Password'),'wrong');await user.click(screen.getByRole('button',{name:'Sign in to demo'}));expect(screen.getByRole('alert')).toHaveTextContent('Sign-in failed (simulated)');
});
it('API empty and network failure remain distinct UI states without mock profiles',async()=>{
 const user=userEvent.setup();let fail=false;const transport=vi.fn(async(input:RequestInfo|URL)=>{if(String(input).endsWith('/session'))return new Response(JSON.stringify(sessions.pro));if(fail)throw new Error('offline');return new Response('[]');});const service=new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:'https://backend.example'},transport);
 localStorage.setItem('carelink-v2-language','en');render(<App service={service}/>);expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();await user.click(screen.getByRole('button',{name:'Load authenticated session'}));await screen.findByText('No authorized patients');expect(screen.queryByText('Lin Zhiqiu')).not.toBeInTheDocument();fail=true;await user.click(screen.getByRole('button',{name:'Refresh'}));await screen.findByText('Unable to load');expect(screen.queryByText('Lin Zhiqiu')).not.toBeInTheDocument();
});
it('priority shortcuts open the right patient and detail sections support arrow-key navigation',async()=>{
 const user=userEvent.setup();render(<App service={new MockDataService()}/>);await user.click(screen.getByRole('button',{name:'English'}));await user.click(screen.getByRole('button',{name:'Sign in to demo'}));await user.click(await screen.findByRole('button',{name:'Review Lin Zhiqiu'}));await screen.findByRole('heading',{name:'Lin Zhiqiu'});
 const overview=screen.getByRole('tab',{name:'Overview'});overview.focus();await user.keyboard('{ArrowRight}');expect(screen.getByRole('tab',{name:'10-minute readings'})).toHaveFocus();expect(screen.getByRole('tabpanel',{name:'10-minute readings'})).toBeInTheDocument();await user.keyboard('{End}');expect(screen.getByRole('tab',{name:'Raw data & AI'})).toHaveFocus();expect(screen.getByRole('heading',{name:'AI predictions'})).toBeInTheDocument();await user.keyboard('{Home}');expect(overview).toHaveAttribute('aria-selected','true');expect(screen.queryByRole('heading',{name:'AI predictions'})).not.toBeInTheDocument();
});
it('password visibility changes display only and keeps the entered demo value',async()=>{
 const user=userEvent.setup();render(<App service={new MockDataService()}/>);await user.click(screen.getByRole('button',{name:'English'}));expect(screen.getByLabelText('Password')).toHaveAttribute('type','password');await user.click(screen.getByRole('button',{name:'Show'}));expect(screen.getByLabelText('Password')).toHaveAttribute('type','text');expect(screen.getByLabelText('Password')).toHaveValue('demo1234');await user.click(screen.getByRole('button',{name:'Hide'}));expect(screen.getByLabelText('Password')).toHaveAttribute('type','password');
});
