/**
 * 实体包级定义。
 * 全局 @FilterDef "tenantFilter" 仅声明一次,避免 Hibernate AnnotationException。
 * 各实体只挂 @Filter(name = "tenantFilter", condition = "tenant_id = :tenantId")。
 *
 * 注意: Hibernate 6 要求 @FilterDef 显式声明 parameters,
 * 否则启用过滤器时报 "Undefined filter parameter [tenantId]"。
 */
@org.hibernate.annotations.FilterDef(
    name = "tenantFilter",
    defaultCondition = "tenant_id = :tenantId",
    parameters = @org.hibernate.annotations.ParamDef(
        name = "tenantId",
        type = java.math.BigInteger.class
    )
)
package com.edu.agent.db.entity;
