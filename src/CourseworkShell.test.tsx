import {expect,it} from 'vitest';
import {render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {CourseworkShell} from './CourseworkShell';
it('gateway starts in API mode; only explicit DEMO selection opens simulated nurse UI',async()=>{
 render(<CourseworkShell/>);expect(screen.queryByRole('button',{name:'Open nurse demo'})).not.toBeInTheDocument();
 await userEvent.click(screen.getByRole('button',{name:'离线演示 / Offline demo'}));expect(screen.getByText('DEMO · 模拟数据 · 离线演示')).toBeInTheDocument();
 await userEvent.click(screen.getByRole('button',{name:'Open nurse demo'}));
 expect(await screen.findByRole('heading',{name:'Readings'})).toBeInTheDocument();expect(screen.getByText('NURSE WORKSPACE')).toBeInTheDocument();
});
it('invalid live endpoint is rejected without pretending hardware is connected',async()=>{
 render(<CourseworkShell/>);const user=userEvent.setup();await user.type(screen.getByRole('textbox',{name:'Mac HTTPS API'}),'http://127.0.0.1:8000');await user.click(screen.getByRole('button',{name:'连接 HTTPS / Connect'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('HTTPS');expect(screen.queryByRole('button',{name:'Open nurse demo'})).not.toBeInTheDocument();expect(screen.getByText(/LIVE · Mac/)).toBeInTheDocument();
});
