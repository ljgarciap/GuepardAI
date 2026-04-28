import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService } from '../../services/brand.service';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-asset-library',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './asset-library.component.html',
  styleUrl: './asset-library.component.css'
})
export class AssetLibraryComponent implements OnInit {
  private brandService = inject(BrandService);
  baseUrl = environment.baseUrl;

  brands: any[] = [];
  selectedBrandId: number | null = null;
  activeTab: 'images' | 'blueprints' | 'knowledge' | 'portfolios' = 'images';

  images: any[] = [];
  blueprints: any[] = [];
  knowledge: any[] = [];
  portfolios: any[] = [];

  selectedAsset: any = null;
  showModal = false;

  ngOnInit() {
    this.loadBrands();
    this.refreshLibrary();
  }

  loadBrands() {
    this.brandService.getBrands().subscribe({
      next: (res) => this.brands = res,
      error: (err) => console.error('Error loading brands:', err)
    });
  }

  setTab(tab: 'images' | 'blueprints' | 'knowledge' | 'portfolios') {
    this.activeTab = tab;
    this.refreshLibrary();
  }

  onBrandChange() {
    this.refreshLibrary();
  }

  openDetail(asset: any) {
    this.selectedAsset = asset;
    this.showModal = true;
  }

  closeDetail() {
    this.showModal = false;
    this.selectedAsset = null;
  }

  refreshLibrary() {
    const bId = this.selectedBrandId || undefined;
    
    if (this.activeTab === 'images') {
      this.brandService.getLibraryImages(bId).subscribe(res => this.images = res);
    } else if (this.activeTab === 'blueprints') {
      this.brandService.getLibraryBlueprints(bId).subscribe(res => this.blueprints = res);
    } else if (this.activeTab === 'knowledge') {
      this.brandService.getLibraryKnowledge(bId).subscribe(res => this.knowledge = res);
    } else if (this.activeTab === 'portfolios') {
      this.brandService.getLibraryPortfolios(bId).subscribe(res => this.portfolios = res);
    }
  }
}
