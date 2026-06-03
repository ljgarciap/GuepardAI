import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { BrandService } from '../../../services/brand.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.css'
})
export class SidebarComponent {
  constructor(private brandService: BrandService) {}

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
