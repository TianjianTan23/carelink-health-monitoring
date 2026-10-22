import type {AppConfig} from './config';
import {validateConfig} from './config';
import {LiveApiService} from './LiveApiService';
import {MockDataService} from './MockDataService';
import type {DataService} from './service';
export function createDataService(input:AppConfig):DataService{const config=validateConfig(input);return config.mode==='mock'?new MockDataService():new LiveApiService(config);}
