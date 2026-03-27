"use client";

import React from "react";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
} from "chart.js";
import { Pie, Bar, Doughnut } from "react-chartjs-2";
import styles from "./page.module.css";

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title);

const CHART_COLORS = {
  terracotta: "rgba(224, 122, 95, 0.8)",
  darkTerracotta: "rgba(180, 80, 60, 0.8)",
  sand: "rgba(244, 241, 222, 0.8)",
  sage: "rgba(129, 178, 154, 0.8)",
  navy: "rgba(61, 64, 91, 0.8)",
  gold: "rgba(242, 204, 143, 0.8)",
  slate: "rgba(100, 110, 120, 0.8)"
};

// Based on Posth et al. 2021: "The origin and legacy of the Etruscans"
const admixtureData = {
  labels: ["Iron Age Etruscans", "Imperial Rome", "Late Antiquity"],
  datasets: [
    {
      label: "Anatolian Neolithic (EEF)",
      data: [60, 45, 50],
      backgroundColor: CHART_COLORS.terracotta,
    },
    {
      label: "Steppe (Yamnaya)",
      data: [35, 10, 20],
      backgroundColor: CHART_COLORS.sage,
    },
    {
      label: "Western Hunter-Gatherer",
      data: [5, 5, 5],
      backgroundColor: CHART_COLORS.navy,
    },
    {
      label: "Iran Neo / Caucasus",
      data: [0, 40, 25],
      backgroundColor: CHART_COLORS.gold,
    },
  ],
};

const yDnaData = {
  labels: ["J2b", "R1b", "G2a", "I2a", "E1b", "Other"],
  datasets: [
    {
      label: "Iron Age Y-Haplogroups",
      data: [30, 25, 20, 10, 10, 5],
      backgroundColor: [
        CHART_COLORS.terracotta,
        CHART_COLORS.sage,
        CHART_COLORS.navy,
        CHART_COLORS.gold,
        CHART_COLORS.slate,
        CHART_COLORS.darkTerracotta
      ],
      borderWidth: 0,
    },
  ],
};

const mtDnaData = {
  labels: ["H", "J", "T", "U5", "K", "Other"],
  datasets: [
    {
      label: "Iron Age mt-Haplogroups",
      data: [40, 15, 15, 10, 10, 10],
      backgroundColor: [
        CHART_COLORS.darkTerracotta,
        CHART_COLORS.navy,
        CHART_COLORS.terracotta,
        CHART_COLORS.gold,
        CHART_COLORS.sage,
        CHART_COLORS.slate
      ],
      borderWidth: 0,
    },
  ],
};

export default function GeneticsPage() {
  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>
      <h1 className="page-heading">Archaeogenetics</h1>
      
      <div className={styles.dashboard}>
        <section className={styles.intro}>
          <h2>The Genetic Profile of the Etruscans</h2>
          <p>
            Recent archaeogenetic studies, particularly the landmark 2021 study by <em>Posth et al.</em>, have fundamentally shifted our understanding of Etruscan origins. While the Etruscan language is a non-Indo-European isolate, DNA analysis of 48 individuals from Tarquinia and Volterra spanning 800 BCE to 1 BCE reveals that Iron Age Etruscans shared a highly similar genetic profile with their Latin-speaking neighbors in Rome.
          </p>
          <p>
            This suggests that the Etruscan language is a relic of local pre-Indo-European continuity, rather than the result of a recent mass migration from Anatolia as proposed by Herodotus. Their genetics show deep continuity with the surrounding populations of the Italian peninsula, featuring a strong component of Steppe-related ancestry that arrived during the Bronze Age.
          </p>
        </section>

        <section className={styles.grids}>
          <div className={styles.chartCard} style={{ gridColumn: "1 / -1" }}>
            <h2>Admixture Components Over Time</h2>
            <p>Major ancestral components in Central Italy across three time periods.</p>
            <div style={{ height: "400px", width: "100%", display: 'flex', justifyContent: 'center' }}>
              <Bar 
                data={admixtureData} 
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: {
                    x: { stacked: true },
                    y: { 
                      stacked: true, 
                      max: 100,
                      ticks: { callback: (val) => `${val}%` }
                    }
                  },
                  plugins: {
                    legend: { position: 'bottom' }
                  }
                }} 
              />
            </div>
          </div>

          <div className={styles.chartCard}>
            <h2>Paternal Lineages (Y-DNA)</h2>
            <p>Distribution of Y-chromosome haplogroups among Iron Age Etruscan males.</p>
            <div style={{ height: "300px", width: "100%" }}>
              <Doughnut 
                data={yDnaData} 
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { position: 'right' } },
                  cutout: '60%'
                }}
              />
            </div>
          </div>

          <div className={styles.chartCard}>
            <h2>Maternal Lineages (mtDNA)</h2>
            <p>Distribution of mitochondrial haplogroups indicating localized continuity.</p>
            <div style={{ height: "300px", width: "100%" }}>
              <Pie 
                data={mtDnaData} 
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { position: 'right' } }
                }}
              />
            </div>
          </div>
        </section>

        <section className={styles.intro} style={{ marginTop: "1rem" }}>
          <h3>Integrating Genetics & Epigraphy</h3>
          <p>
            By mapping these genetic findings against the epigraphic dataset, we can observe the social structure of Etruscan society. The continuity of their language despite genetic mixture with Steppe-ancestry populations points to a resilient local culture that assimilated newcomers rather than being erased by them. Over the coming iterations, this module will correlate regional epigraphic variations with micro-regional genetic drift patterns.
          </p>
        </section>
      </div>
    </div>
  );
}
