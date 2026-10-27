package com.edu.agent.db.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.io.Serializable;
import java.math.BigInteger;
import java.util.Objects;

@Getter
@Setter
@NoArgsConstructor
@Entity
@Table(name = "knowledge_prerequisites")
@IdClass(KnowledgePrerequisite.PK.class)
public class KnowledgePrerequisite {

    @Id
    @Column(name = "node_id", nullable = false)
    private BigInteger nodeId;

    @Id
    @Column(name = "prerequisite_id", nullable = false)
    private BigInteger prerequisiteId;

    @Getter
    @Setter
    @NoArgsConstructor
    public static class PK implements Serializable {
        private BigInteger nodeId;
        private BigInteger prerequisiteId;

        public PK(BigInteger nodeId, BigInteger prerequisiteId) {
            this.nodeId = nodeId;
            this.prerequisiteId = prerequisiteId;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof PK pk)) return false;
            return Objects.equals(nodeId, pk.nodeId) && Objects.equals(prerequisiteId, pk.prerequisiteId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(nodeId, prerequisiteId);
        }
    }
}
