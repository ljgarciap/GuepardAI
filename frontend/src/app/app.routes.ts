import { Routes } from '@angular/router';
import { GeneratorComponent } from './pages/generator/generator.component';
import { BrandHubComponent } from './pages/brand-hub/brand-hub.component';
import { BrandManagerComponent } from './pages/brand-manager/brand-manager.component';
import { AssetLibraryComponent } from './pages/asset-library/asset-library.component';
import { TemplateMergeComponent } from './pages/template-merge/template-merge.component';
import { AdminComponent } from './pages/admin/admin.component';
import { LoginComponent } from './pages/login/login.component';
import { RegisterComponent } from './pages/register/register.component';
import { TosComponent } from './pages/tos/tos.component';
import { authGuard } from './guards/auth.guard';
import { roleGuard } from './guards/role.guard';
import { tosGuard } from './guards/tos.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, title: 'Sign In' },
  { path: 'register', component: RegisterComponent, title: 'Create Account' },
  { path: 'tos', component: TosComponent, title: 'Terms of Service', canActivate: [authGuard] },
  { path: '', component: GeneratorComponent, title: 'AI Generator Studio', canActivate: [authGuard, tosGuard] },
  { path: 'template-merge', component: TemplateMergeComponent, title: 'Template Merge Studio', canActivate: [authGuard, tosGuard] },
  { path: 'brands', component: BrandHubComponent, title: 'Intelligence Hub', canActivate: [authGuard, tosGuard] },
  { path: 'directory', component: BrandManagerComponent, title: 'Brand Directory Master', canActivate: [authGuard, tosGuard] },
  { path: 'library', component: AssetLibraryComponent, title: 'Strategic Asset Library', canActivate: [authGuard, tosGuard] },
  { path: 'admin', component: AdminComponent, title: 'Admin Panel', canActivate: [authGuard, tosGuard, roleGuard], data: { roles: ['admin', 'superadmin'] } },
  { path: '**', redirectTo: '' }
];
