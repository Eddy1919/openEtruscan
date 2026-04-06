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
import { Bar, Doughnut } from "react-chartjs-2";
import { AldineManuscript } from "@/components/aldine/Manuscript";
import { Row, Box, Stack, Ornament } from "@/components/aldine/Layout";

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title);

const ALDINE_CHART = {
  accent: "#A2574B",
  sage: "#8E706A",
  ink: "#2B211E",
  bone: "#f4f2eb",
  navy: "#544641",
  gold: "#8c6b5d",
};

const admixtureData = {
  labels: ["Iron Age Etruscans", "Imperial Rome", "Late Antiquity"],
  datasets: [
    {
      label: "Anatolian Neolithic (EEF)",
      data: [60, 45, 50],
      backgroundColor: ALDINE_CHART.accent,
    },
    {
      label: "Steppe (Yamnaya)",
      data: [35, 10, 20],
      backgroundColor: ALDINE_CHART.sage,
    },
    {
      label: "Western Hunter-Gatherer",
      data: [5, 5, 5],
      backgroundColor: ALDINE_CHART.navy,
    },
    {
      label: "Iran Neo / Caucasus",
      data: [0, 40, 25],
      backgroundColor: ALDINE_CHART.gold,
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
        ALDINE_CHART.accent,
        ALDINE_CHART.sage,
        ALDINE_CHART.navy,
        ALDINE_CHART.gold,
        "#7c6b5d",
        "#2B211E"
      ],
      borderWidth: 0,
    },
  ],
};

export default function GeneticsPage() {
  return (
    <Box className="aldine-canvas aldine-w-full" padding={6}>
      <AldineManuscript align="center">
        
       <Stack border="bottom" padding={4} style={{ marginBottom: "var(--aldine-space-3xl)" }}>
          <div style={{ marginBottom: "var(--aldine-space-sm)" }}><Ornament.Heading className="aldine-italic">
            Archaeogenetics Matrix
          </Ornament.Heading></div>
          <p className="aldine-ink-muted aldine-font-editorial aldine-leading-relaxed" style={{ fontSize: "1.125rem", maxWidth: "48rem" }}>
            Biological origins and ancestral migration topologies of the Etruscan civilization synthesized via ancient DNA (aDNA) modeling.
          </p>
        </Stack>

        <Stack gap={12} style={{ marginBottom: "var(--aldine-space-4xl)" }}>
           <Stack gap={12} className="aldine-w-full">
              <Box border="left" style={{ paddingLeft: "var(--aldine-space-xl)", paddingTop: "var(--aldine-space-md)", paddingBottom: "var(--aldine-space-md)", borderLeftWidth: '4px', borderLeftColor: 'var(--aldine-accent)' }}>
                <h2 className="aldine-display-title aldine-italic" style={{ fontSize: '1.25rem', marginBottom: 'var(--aldine-space-lg)' }}>The Genetic Profile</h2>
                <Stack gap={6} className="aldine-font-editorial aldine-ink-base aldine-leading-relaxed" style={{ fontSize: '1.125rem', maxWidth: '48rem' }}>
                  <p>
                    Recent archaeogenetic studies, particularly the landmark 2021 study by <em>Posth et al.</em>, have fundamentally shifted our understanding of Etruscan origins. While the Etruscan language is a non-Indo-European isolate, DNA analysis reveals that Iron Age Etruscans shared a highly similar genetic profile with their Latin-speaking neighbors in Rome.
                  </p>
                  <p>
                    This suggests that the Etruscan language is a relic of local pre-Indo-European continuity, rather than the result of a recent mass migration from Anatolia. Their genetics show deep continuity with the surrounding populations of the Italian peninsula, featuring a strong component of Steppe-related ancestry that arrived during the Bronze Age.
                  </p>
                </Stack>
              </Box>

              <Box surface="bone" border="all" padding={6} style={{ marginTop: 'var(--aldine-space-2xl)' }}>
                <Stack gap={2} align="center" border="bottom" padding={4} style={{ marginBottom: 'var(--aldine-space-2xl)' }}>
                   <Ornament.Label className="aldine-accent">Admixture Temporal Vectors</Ornament.Label>
                   <span className="aldine-font-interface aldine-ink-muted aldine-uppercase" style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.1em' }}>Primary Ancestral Components</span>
                </Stack>
                
                <div className="aldine-w-full aldine-flex-col aldine-items-center" style={{ height: '450px' }}>
                  <Bar 
                    data={admixtureData} 
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      scales: {
                        x: { stacked: true, grid: { display: false }, ticks: { color: '#2B211E', font: { family: 'inherit', size: 10 } } },
                        y: { 
                          stacked: true, 
                          max: 100,
                          grid: { color: 'rgba(43,33,30,0.05)' },
                          ticks: { callback: (val) => `${val}%`, color: '#2B211E', font: { size: 10 } }
                        }
                      },
                      plugins: {
                        legend: { position: 'bottom', labels: { color: '#2B211E', padding: 30, font: { size: 10, weight: 'bold' } } }
                      }
                    }} 
                  />
                </div>
              </Box>
           </Stack>
        </Stack>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--aldine-space-3xl)', marginBottom: 'var(--aldine-space-4xl)', alignItems: 'center' }}>
           <Box style={{ flex: '1 1 300px' }}>
              <div style={{ height: '350px', width: '100%' }}>
                <Doughnut 
                  data={yDnaData} 
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    cutout: '82%'
                  }}
                />
              </div>
           </Box>

           <Stack gap={8} style={{ flex: '1 1 300px' }}>
              <Stack gap={4}>
                 <h2 className="aldine-display-title" style={{ fontSize: '1.125rem', borderBottom: '1px solid var(--aldine-hairline)', paddingBottom: 'var(--aldine-space-md)', marginBottom: 'var(--aldine-space-lg)' }}>Paternal Y-DNA Distribution</h2>
                 <div style={{ marginBottom: 'var(--aldine-space-xl)' }}><Ornament.Label className="aldine-accent">Iron Age Haplogroups (N=82)</Ornament.Label></div>
                 
                 <Stack gap={4}>
                    {yDnaData.labels.map((l, i) => (
                      <Row key={l} justify="between" align="center" className="aldine-group">
                         <Row gap={3} align="center">
                            <div style={{ width: '8px', height: '8px', borderRadius: '9999px', backgroundColor: (yDnaData.datasets[0].backgroundColor as string[])[i] }} />
                            <span className="aldine-font-interface aldine-ink-muted aldine-transition" style={{ fontSize: '0.75rem', fontWeight: 600 }}>{l}</span>
                         </Row>
                         <span className="aldine-font-mono aldine-ink-base" style={{ fontSize: '0.875rem' }}>{(yDnaData.datasets[0].data[i] as number).toFixed(1)}%</span>
                      </Row>
                    ))}
                 </Stack>
              </Stack>

              <Box border="left" padding={4} surface="bone" style={{ borderLeftWidth: '2px', borderLeftColor: 'var(--aldine-accent)' }}>
                <div style={{ marginBottom: 'var(--aldine-space-sm)' }}><Ornament.Label className="aldine-accent">Sociolinguistic Inference</Ornament.Label></div>
                <p className="aldine-font-editorial aldine-ink-muted aldine-leading-relaxed aldine-italic" style={{ fontSize: '1rem' }}>
                  Mapping genetic findings against epigraphic datasets suggests a resilient linguistic core. The continuity of their language despite deep genetic integration points to a profound cultural dominance.
                </p>
              </Box>
           </Stack>
        </div>

        <Row justify="center" padding={6} border="top" style={{ width: '100%', opacity: 0.3, marginTop: 'var(--aldine-space-2xl)', borderStyle: 'dashed', borderColor: 'var(--aldine-ink)' }}>
          <p className="aldine-font-interface aldine-uppercase aldine-ink-base aldine-text-center" style={{ fontSize: '0.75rem', letterSpacing: '0.2em', fontWeight: 600 }}>
             Reference Citation: Posth et al. (2021) "The origin and legacy of the Etruscans" • Science Advances (Vol 7, eabi7673)
          </p>
        </Row>

      </AldineManuscript>
    </Box>
  );
}
