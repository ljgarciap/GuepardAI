import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { interval, switchMap, takeWhile, Subscription } from 'rxjs';
import {
  ArtisticV2Service,
  EligibleBrand,
  GenerationStatus,
} from '../../services/artistic-v2.service';
import { environment } from '../../../environments/environment';

/**
 * artistic-studio.component.ts — Artistic Generation Engine v2 (Phase 4).
 * docs/specs/artistic-generation-v2.md
 *
 * Isolated route/entry point, per the feature's non-negotiable constraint:
 * v1's Synthesis Studio (GeneratorComponent) is never touched. This page
 * fires a v1 job and a v2_artistic job for the SAME brand/prompt side by
 * side, so Luis can compare output before any promote/retire decision
 * (Phase 4 acceptance criterion) — no shared component edited in place.
 */

interface ColumnState {
  jobId: number | null;
  status: GenerationStatus | null;
  isRunning: boolean;
  error: string | null;
}

function freshColumn(): ColumnState {
  return { jobId: null, status: null, isRunning: false, error: null };
}

@Component({
  selector: 'app-artistic-studio',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './artistic-studio.component.html',
  styleUrl: './artistic-studio.component.css',
})
export class ArtisticStudioComponent implements OnInit {
  private artisticV2 = inject(ArtisticV2Service);
  private baseUrl = environment.baseUrl;

  eligibleBrands: EligibleBrand[] = [];
  selectedBrandId: number | null = null;
  prompt = '';
  loadError: string | null = null;
  isLoadingBrands = true;

  v1 = freshColumn();
  v2 = freshColumn();

  private v1Poll?: Subscription;
  private v2Poll?: Subscription;

  ngOnInit() {
    this.artisticV2.getEligibleBrands().subscribe({
      next: (res) => {
        this.eligibleBrands = res.brands;
        this.isLoadingBrands = false;
        if (this.eligibleBrands.length > 0) {
          this.selectedBrandId = this.eligibleBrands[0].id;
        }
      },
      error: () => {
        this.isLoadingBrands = false;
        this.loadError = 'Could not load brands with mined layout grammar.';
      },
    });
  }

  get canGenerate(): boolean {
    return !!this.selectedBrandId && this.prompt.trim().length > 0 && !this.v1.isRunning && !this.v2.isRunning;
  }

  // Drives the comparison grid's visibility. Deliberately NOT jobId-based —
  // jobId is only set once the initial POST resolves, so gating on it left
  // the grid (and any error message) invisible until then, or forever on a
  // failed request. See the template comment for the real bug this fixes.
  get hasStarted(): boolean {
    return this.v1.isRunning || this.v2.isRunning || !!this.v1.jobId || !!this.v2.jobId
      || !!this.v1.error || !!this.v2.error;
  }

  generateBoth() {
    if (!this.canGenerate || !this.selectedBrandId) return;

    this.v1 = { ...freshColumn(), isRunning: true };
    this.v2 = { ...freshColumn(), isRunning: true };

    const req = { brand_id: this.selectedBrandId, prompt: this.prompt.trim() };

    this.artisticV2.generateV1(req).subscribe({
      next: (res) => {
        this.v1.jobId = res.job_id;
        this.pollColumn('v1');
      },
      error: (err) => {
        this.v1.isRunning = false;
        this.v1.error = err.error?.detail || 'v1 generation failed to start.';
      },
    });

    this.artisticV2.generate(req).subscribe({
      next: (res) => {
        this.v2.jobId = res.job_id;
        this.pollColumn('v2');
      },
      error: (err) => {
        this.v2.isRunning = false;
        this.v2.error = err.error?.detail || 'v2 generation failed to start.';
      },
    });
  }

  private pollColumn(which: 'v1' | 'v2') {
    const column = which === 'v1' ? this.v1 : this.v2;
    if (!column.jobId) return;

    const poll$ = interval(2000).pipe(
      switchMap(() => this.artisticV2.getGenerationStatus(column.jobId!)),
      takeWhile((res) => res.status !== 'completed' && res.status !== 'error', true)
    );

    const sub = poll$.subscribe({
      next: (res) => {
        column.status = res;
        if (res.status === 'completed' || res.status === 'error') {
          column.isRunning = false;
          if (res.status === 'error') column.error = res.current_step;
        }
      },
      error: () => {
        column.isRunning = false;
        column.error = 'Communication link lost during generation.';
      },
    });

    if (which === 'v1') this.v1Poll = sub;
    else this.v2Poll = sub;
  }

  downloadUrl(column: ColumnState): string | null {
    return column.status?.download_url ? this.baseUrl + column.status.download_url : null;
  }

  reset() {
    this.v1Poll?.unsubscribe();
    this.v2Poll?.unsubscribe();
    this.v1 = freshColumn();
    this.v2 = freshColumn();
    this.prompt = '';
  }
}
