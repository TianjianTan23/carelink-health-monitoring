import React from 'react';
import {expect,it,vi} from 'vitest';
import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {App} from './App';
import {MockDataService} from './data/MockDataService';
import {LiveApiService} from './data/LiveApiService';
import {defaultConfig} from './data/config';
import sessions from '../shared/demo-sessions.json';

async function loginAs(kind:'Patient'|'Nurse'){
  const user=userEvent.setup();
  render(<App service={new MockDataService()}/>);
  await user.type(screen.getByLabelText('User ID'),kind==='Patient'?'demo-patient':'demo-clinician');
  await user.type(screen.getByLabelText('Password'),kind==='Patient'?'coursework-demo':'coursework-demo');
  await user.click(screen.getByRole('button',{name:'Sign in'}));
  await screen.findByRole('heading',{name:'Readings'});
  return user;
}

it('patient credentials open a patient-scoped view with every required section and optional SpO2',async()=>{
  const user=await loginAs('Patient');
  expect(screen.getByText('PATIENT VIEW')).toBeInTheDocument();
  expect(screen.getByText('SpO₂')).toBeInTheDocument();
  for(const name of ['Readings','History','Charts','Classifications','Alert history','Settings'])expect(screen.getByRole('button',{name})).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'History'}));await screen.findByRole('heading',{name:'History'});expect(await screen.findAllByRole('row')).toHaveLength(22);
  await user.click(screen.getByRole('button',{name:'Charts'}));expect(await screen.findByRole('heading',{name:'Heart rate'})).toBeInTheDocument();expect(screen.getByRole('heading',{name:'Temperature'})).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Classifications'}));expect(await screen.findByRole('heading',{name:'Classifications & confidence'})).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Settings'}));expect(screen.getByText('ttj')).toBeInTheDocument();expect(screen.getByText('Patient view')).toBeInTheDocument();
});

it('nurse credentials open the nurse workspace and permit alert acknowledgement',async()=>{
  const user=await loginAs('Nurse');
  expect(screen.getByText('NURSE WORKSPACE')).toBeInTheDocument();
  expect(screen.getByRole('alert',{name:/CRITICAL|WARNING/})).toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Alert history'}));
  await screen.findByRole('heading',{name:'Alerts'});
  const alertCards=await screen.findAllByRole('button',{name:/p001|Lin Zhiqiu/});
  await user.click(alertCards[0]);
  const acknowledge=screen.getByRole('button',{name:'Acknowledge alert'});
  expect(acknowledge).toBeEnabled();
});

it('patient cannot acknowledge alerts',async()=>{
  const user=userEvent.setup();const service=new MockDataService();await service.getSession('basic');service.setScenario('p004','fall');render(<App service={service}/>);
  await user.type(screen.getByLabelText('User ID'),'demo-patient');await user.type(screen.getByLabelText('Password'),'coursework-demo');await user.click(screen.getByRole('button',{name:'Sign in'}));await screen.findByRole('heading',{name:'Readings'});
  await user.click(screen.getByRole('button',{name:'Alert history'}));
  await screen.findByRole('heading',{name:'Alerts'});
  const cards=await screen.findAllByRole('button',{name:/p004|Xu Wangshu/});
  await user.click(cards[0]);
  expect(screen.queryByRole('button',{name:'Acknowledge alert'})).not.toBeInTheDocument();
  expect(screen.getByText('Clinicians handle alert acknowledgements.')).toBeInTheDocument();
});

it('login validates missing and incorrect credentials',async()=>{
  const user=userEvent.setup();render(<App service={new MockDataService()}/>);
  await user.click(screen.getByRole('button',{name:'Sign in'}));expect(screen.getByRole('alert')).toHaveTextContent('Enter a user ID and password');
  await user.type(screen.getByLabelText('User ID'),'demo-patient');await user.type(screen.getByLabelText('Password'),'wrong');await user.click(screen.getByRole('button',{name:'Sign in'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid user ID or password');
});

it('live API empty and network failure remain distinct without mock fallback',async()=>{
  const user=userEvent.setup();let fail=false;
  const transport=vi.fn(async(input:RequestInfo|URL)=>{
    const url=String(input);
    if(url.endsWith('/api/login'))return new Response(JSON.stringify(sessions.pro));
    if(fail)throw new Error('offline');
    return new Response('[]',{headers:{'Content-Type':'application/json'}});
  });
  const service=new LiveApiService({...defaultConfig,mode:'live',apiConfirmed:true,baseUrl:'https://backend.example'},transport);
  render(<App service={service}/>);
  await user.type(screen.getByLabelText('User ID'),'demo-clinician');await user.type(screen.getByLabelText('Password'),'coursework-demo');await user.click(screen.getByRole('button',{name:'Sign in'}));
  await screen.findByText('No authorized patients');
  fail=true;await user.click(screen.getByRole('button',{name:'Refresh'}));
  await screen.findByText('Unable to load');
  expect(screen.queryByText('Lin Zhiqiu')).not.toBeInTheDocument();
});

it('never displays account credentials and keeps the password masked',async()=>{
  const user=userEvent.setup();render(<App service={new MockDataService()}/>);
  expect(screen.getByLabelText('Password')).toHaveAttribute('type','password');
  expect(screen.queryByRole('button',{name:'Show'})).not.toBeInTheDocument();
  expect(screen.queryByText(/synthetic-test-password|another-test-password/)).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('User ID'),'demo-patient');await user.type(screen.getByLabelText('Password'),'coursework-demo');
  await waitFor(()=>expect(screen.getByLabelText('Password')).toHaveAttribute('type','password'));
});

it('clears private views and reports an unconfirmed server logout',async()=>{
 const user=userEvent.setup();
 const service=new MockDataService();
 vi.spyOn(service,'logout').mockRejectedValue(new Error('synthetic server failure'));
 render(<App service={service}/>);
 // Use the explicit mock session, never a real account credential.
 vi.spyOn(service,'authenticate').mockResolvedValue(sessions.pro as Awaited<ReturnType<typeof service.authenticate>>);
 await user.type(screen.getByLabelText('User ID'),'fixture');
 await user.type(screen.getByLabelText('Password'),'synthetic-test-password');
 await user.click(screen.getByRole('button',{name:'Sign in'}));
 await screen.findByRole('heading',{name:'Readings'});
 await user.click(screen.getByRole('button',{name:'Sign out'}));
 expect(await screen.findByRole('heading',{name:'Sign in to CareLink'})).toBeInTheDocument();
 expect(screen.getByRole('alert')).toHaveTextContent('Server session revocation could not be confirmed');
 expect(screen.queryByRole('heading',{name:'Readings'})).not.toBeInTheDocument();
});
