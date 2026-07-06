import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { BrandService } from '../../../services/brand.service';
import { ThemeService } from '../../../services/theme.service';
import { AuthService } from '../../../services/auth.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent {
  constructor(
    private brandService: BrandService,
    public themeService: ThemeService,
    public authService: AuthService
  ) {}

  get logoSrc(): string {
    return this.themeService.theme() === 'dark' ? 'logo-dark.png' : 'logo-light.png';
  }

  get userInitial(): string {
    const email = this.authService.currentUser?.email;
    return email ? email.charAt(0).toUpperCase() : '?';
  }

  get isSuperadmin(): boolean {
    return this.authService.currentUser?.role === 'superadmin';
  }

  logout(): void {
    this.authService.logout();
  }

  resetSystem(): void {
    if (confirm('¿Estás seguro de que deseas limpiar COMPLETAMENTE la base de datos y todos los archivos subidos (uploads)? Esta acción no se puede deshacer.')) {
      this.brandService.resetDatabase().subscribe({
        next: (res) => {
          alert('Sistema limpiado y restablecido con éxito.');
          window.location.reload();
        },
        error: (err) => {
          console.error(err);
          alert('Error al intentar limpiar el sistema.');
        }
      });
    }
  }
}
