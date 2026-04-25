import { Routes } from '@angular/router';
import { GeneratorComponent } from './pages/generator/generator.component';
import { BrandHubComponent } from './pages/brand-hub/brand-hub.component';

export const routes: Routes = [
  { path: '', component: GeneratorComponent, title: 'AI Generator Studio' },
  { path: 'brands', component: BrandHubComponent, title: 'Brand Hub Manager' },
  { path: '**', redirectTo: '' }
];
