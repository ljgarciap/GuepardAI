import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../services/auth.service';
import { ThemeService } from '../../services/theme.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css'
})
export class LoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  themeService = inject(ThemeService);

  get logoSrc(): string {
    return this.themeService.theme() === 'dark' ? 'logo-dark-transparent.png' : 'logo-light-transparent.png';
  }

  email = '';
  password = '';
  isLoading = false;
  errorMessage: string | null = null;

  submit(): void {
    if (!this.email || !this.password || this.isLoading) return;

    this.isLoading = true;
    this.errorMessage = null;

    this.authService.login(this.email, this.password).subscribe({
      next: () => {
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/';
        this.router.navigateByUrl(returnUrl);
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading = false;
        this.errorMessage = err.status === 429
          ? 'Too many attempts. Please try again in a few minutes.'
          : 'Incorrect email or password.';
      },
    });
  }
}
