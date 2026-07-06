import { Routes } from '@angular/router';
import { GeneratorComponent } from './pages/generator/generator.component';
import { BrandHubComponent } from './pages/brand-hub/brand-hub.component';
import { BrandManagerComponent } from './pages/brand-manager/brand-manager.component';
import { AssetLibraryComponent } from './pages/asset-library/asset-library.component';
import { TemplateMergeComponent } from './pages/template-merge/template-merge.component';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, title: 'Sign In' },
  { path: 'register', component: RegisterComponent, title: 'Create Account' },
  { path: '', component: GeneratorComponent, title: 'AI Generator Studio', canActivate: [authGuard] },
  { path: 'template-merge', component: TemplateMergeComponent, title: 'Template Merge Studio', canActivate: [authGuard] },
  { path: 'brands', component: BrandHubComponent, title: 'Intelligence Hub', canActivate: [authGuard] },
  { path: 'directory', component: BrandManagerComponent, title: 'Brand Directory Master', canActivate: [authGuard] },
  { path: 'library', component: AssetLibraryComponent, title: 'Strategic Asset Library', canActivate: [authGuard] },
  { path: '**', redirectTo: '' }
];
