import { Component, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService } from '../../services/brand.service';
import { interval, Subscription, switchMap, takeWhile } from 'rxjs';

interface JobState {
  file: File | null;
  loading: boolean;
  status: string;
  progress: number;
  successMessage: string;
  errorMessage: string;
  pollingSub?: Subscription;
  logs: { time: string, role: string, message: string }[];
}

@Component({
  selector: 'app-brand-hub',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './brand-hub.component.html',
  styleUrl: './brand-hub.component.css'
})
export class BrandHubComponent implements OnInit, OnDestroy {
  brandService = inject(BrandService);

  identityState: JobState = this.initialState();
  knowledgeState: JobState = this.initialState();

  resetLoading: boolean = false;
  resetSuccess: boolean = false;

  ngOnInit() {
    console.log('[System] Brand Hub Synchronized with Persona-Driven Logs.');
  }

  private initialState(): JobState {
    return {
      file: null,
      loading: false,
      status: '',
      progress: 0,
      successMessage: '',
      errorMessage: '',
      logs: []
    };
  }

  onFileSelected(event: any, type: 'brand_style' | 'knowledge') {
    if (event.target.files.length > 0) {
      const file = event.target.files[0];
      if (type === 'brand_style') this.identityState.file = file;
      else if (type === 'knowledge') this.knowledgeState.file = file;
    }
  }

  private addLog(state: JobState, role: string, message: string) {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    state.logs.push({ time, role, message });
    if (state.logs.length > 8) state.logs.shift();
  }

  upload(type: 'brand_style' | 'knowledge') {
    const state = type === 'brand_style' ? this.identityState : this.knowledgeState;

    if (!state.file) {
      state.errorMessage = 'Validation: Document required.';
      return;
    }
    
    state.loading = true;
    state.status = 'Initializing upload...';
    state.progress = 5;
    state.errorMessage = '';
    state.successMessage = '';
    state.logs = [];

    const role = type === 'brand_style' ? 'Designer' : 'Analyst';
    this.addLog(state, 'Strategic Orchestrator', `Initiating ${type.replace('_', ' ')} ingestion...`);

    const filename = state.file.name;
    
    this.brandService.uploadBrandAsset(state.file, type).subscribe({
      next: (res) => {
        this.addLog(state, role, 'Document received. Starting architectural mapping...');
        this.startPolling(filename, type);
      },
      error: (err) => {
        state.loading = false;
        state.errorMessage = err.error?.detail || err.message || 'Server timeout.';
      }
    });
  }

  startPolling(filename: string, type: 'brand_style' | 'knowledge') {
    const state = type === 'brand_style' ? this.identityState : this.knowledgeState;

    state.pollingSub?.unsubscribe();

    state.pollingSub = interval(2000)
      .pipe(
        switchMap(() => this.brandService.getIngestionStatus(filename, type)),
        takeWhile((res) => res.status === 'processing' || res.status === 'pending' || res.status === 'none', true)
      )
      .subscribe({
        next: (res) => {
          state.status = this.mapStatus(res.current_step);
          state.progress = res.progress || 0;

          const lastLog = state.logs[state.logs.length - 1];
          const mappedRole = this.mapRole(res.current_step, type);
          const mappedMsg = this.mapStatus(res.current_step);

          if (lastLog?.message !== mappedMsg && mappedMsg) {
            this.addLog(state, mappedRole, mappedMsg);
          }

          if (res.status === 'completed') {
            state.progress = 100;
            this.addLog(state, 'Strategic Orchestrator', 'Ingestion finalized and verified.');
            state.successMessage = 'Ingestion finalized successfully.';
            state.pollingSub?.unsubscribe();
            setTimeout(() => { state.loading = false; }, 5000);
          } else if (res.status === 'error') {
            state.loading = false;
            state.errorMessage = res.current_step;
            state.pollingSub?.unsubscribe();
          }
        },
        error: (err) => {
          state.loading = false;
          state.pollingSub?.unsubscribe();
        }
      });
  }

  private mapRole(step: string, type: string): string {
    if (step.includes('Parsing')) return 'Analyst';
    if (step.includes('Indexing')) return 'Architect';
    return type === 'brand_style' ? 'Designer' : 'Analyst';
  }

  private mapStatus(step: string): string {
    return step.replace(/Gemini|Claude|OpenAI/gi, 'The Intelligence')
               .replace('Extracting', 'Mapping')
               .replace('Generating', 'Synthesizing');
  }

  resetAll() {
    if (!confirm('⚠️ This will DELETE all brand profiles, knowledge vectors, and jobs.\n\nAre you sure?')) return;
    this.resetLoading = true;
    this.brandService.resetDatabase().subscribe({
      next: () => {
        this.resetLoading = false;
        this.identityState = this.initialState();
        this.knowledgeState = this.initialState();
      },
      error: () => { this.resetLoading = false; }
    });
  }

  ngOnDestroy() {
    this.identityState.pollingSub?.unsubscribe();
    this.knowledgeState.pollingSub?.unsubscribe();
  }
}
