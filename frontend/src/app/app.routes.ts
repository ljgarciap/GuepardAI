import { Routes } from '@angular/router';
import { GeneratorComponent } from './pages/generator/generator.component';
import { BrandHubComponent } from './pages/brand-hub/brand-hub.component';
import { BrandManagerComponent } from './pages/brand-manager/brand-manager.component';

export const routes: Routes = [
  { path: '', component: GeneratorComponent, title: 'AI Generator Studio' },
  { path: 'brands', component: BrandHubComponent, title: 'Intelligence Hub' },
  { path: 'directory', component: BrandManagerComponent, title: 'Brand Directory Master' },
  { path: '**', redirectTo: '' }
];
