import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css'
})
export class RegisterComponent {
  private authService = inject(AuthService);
  private router = inject(Router);

  email = '';
  password = '';
  tenantName = '';
  isLoading = false;
  errorMessage: string | null = null;

  submit(): void {
    if (!this.email || !this.password || this.isLoading) return;

    this.isLoading = true;
    this.errorMessage = null;

    this.authService.register(this.email, this.password, this.tenantName || undefined).subscribe({
      next: () => this.router.navigateByUrl('/'),
      error: (err: HttpErrorResponse) => {
        this.isLoading = false;
        this.errorMessage = err.status === 409
          ? 'Ya existe una cuenta con ese email.'
          : 'No se pudo crear la cuenta. Revisa los datos ingresados.';
      },
    });
  }
}
