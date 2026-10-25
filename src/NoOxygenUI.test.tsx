import React from 'react';
import {it,expect} from 'vitest';
import {render,screen,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {App} from './App';
import {MockDataService} from './data/MockDataService';
function noOxygen(){expect(document.body.textContent).not.toMatch(/SpO₂|SpO2|Blood oxygen|血氧|MAX30102/i);}
it('removes retired monitoring from the complete Pro/Basic UI, rules, histories, LCD and scenarios in both languages',async()=>{
 const user=userEvent.setup();render(<App service={new MockDataService()}/>);await user.click(screen.getByRole('button',{name:'English'}));await user.click(screen.getByRole('button',{name:'Sign in to demo'}));await screen.findByRole('heading',{name:/Patients/});noOxygen();
 await user.click(screen.getByRole('button',{name:'Open Lin Zhiqiu'}));await screen.findByRole('heading',{name:'Lin Zhiqiu'});noOxygen();expect(screen.getByRole('region',{name:'Heart-rate monitoring'})).toHaveTextContent('BPM');expect(screen.getByText(/Heart-rate updated/)).toBeInTheDocument();
 for(const name of ['10-minute readings','Raw data & AI','Overview']){await user.click(screen.getByRole('tab',{name}));noOxygen();}
 await user.click(screen.getByRole('button',{name:'Device display'}));noOxygen();await user.click(screen.getByRole('button',{name:'Demo rules'}));noOxygen();
 await user.click(screen.getByRole('button',{name:'Demo scenarios'}));noOxygen();await user.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Close'}));
 await user.click(screen.getByRole('button',{name:'Try Basic mode'}));await screen.findByRole('heading',{name:'Xu Wangshu'});noOxygen();expect(screen.getByRole('region',{name:'Heart-rate monitoring'})).toHaveTextContent('Mock heart rate');await user.click(screen.getByRole('button',{name:'中文'}));noOxygen();expect(screen.getByRole('region',{name:'心率监测'})).toHaveTextContent('心率更新');
});
