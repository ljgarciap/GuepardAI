import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

/**
 * Restringe una ruta a los roles listados en `route.data['roles']`.
 * Uso: { path: 'admin/users', canActivate: [authGuard, roleGuard], data: { roles: ['superadmin', 'admin'] } }
 */
export const roleGuard: CanActivateFn = (route) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const allowedRoles = route.data['roles'] as string[] | undefined;

  const user = authService.currentUser;
  if (!user) {
    return router.createUrlTree(['/login']);
  }
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return router.createUrlTree(['/']);
  }
  return true;
};
